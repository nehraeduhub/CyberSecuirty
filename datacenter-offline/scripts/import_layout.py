#!/usr/bin/env python3
"""Import a data centre layout (rooms, racks, devices, rack positions) into GLPI.

Reads two CSV files and creates or updates the matching GLPI objects through the
GLPI REST API. Uses only the Python standard library, so it runs on an offline
server with a plain Python 3 install.

    python3 import_layout.py --url http://localhost --user glpi \
        --racks ../layout/racks.csv --devices ../layout/devices.csv

Re-running is safe: existing objects are matched by name and updated, and
devices already in GLPI (for example from GLPI Agent inventory) are reused and
simply placed in their rack.
"""

import argparse
import base64
import csv
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Friendly device types -> GLPI itemtypes that can be mounted in a rack
TYPE_ALIASES = {
    "server": "Computer",
    "computer": "Computer",
    "storage": "Computer",
    "appliance": "Computer",
    "switch": "NetworkEquipment",
    "router": "NetworkEquipment",
    "firewall": "NetworkEquipment",
    "network": "NetworkEquipment",
    "networkequipment": "NetworkEquipment",
    "loadbalancer": "NetworkEquipment",
    "pdu": "PDU",
    "ups": "PDU",
    "enclosure": "Enclosure",
    "chassis": "Enclosure",
    "patchpanel": "PassiveDCEquipment",
    "passive": "PassiveDCEquipment",
    "passivedcequipment": "PassiveDCEquipment",
    "cablemanager": "PassiveDCEquipment",
    "blank": "PassiveDCEquipment",
    "kvm": "Peripheral",
    "peripheral": "Peripheral",
    "tape": "Peripheral",
    "monitor": "Monitor",
}

ORIENTATION = {"N": 1, "E": 2, "S": 3, "W": 4}  # Rack::ROOM_O_*
FACE = {"front": 0, "rear": 1}  # Rack::FRONT / Rack::REAR
HPOS = {"": 0, "none": 0, "left": 1, "right": 2}  # Rack::POS_*
PDU_SIDE = {"left": 1, "right": 2, "top": 3, "bottom": 4}  # PDU_Rack::SIDE_*


class GlpiError(Exception):
    pass


class Glpi:
    def __init__(self, url, app_token=None, verify_ssl=True):
        self.base = url.rstrip("/") + "/apirest.php"
        self.headers = {"Content-Type": "application/json"}
        if app_token:
            self.headers["App-Token"] = app_token
        self.ctx = None
        if not verify_ssl:
            import ssl

            self.ctx = ssl._create_unverified_context()

    def _call(self, method, path, body=None, extra_headers=None, query=None):
        url = self.base + "/" + path.lstrip("/")
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = dict(self.headers)
        headers.update(extra_headers or {})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=60) as resp:
                raw = resp.read().decode() or "null"
                return json.loads(raw), resp.headers
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise GlpiError(f"{method} {path}: HTTP {e.code} {detail}") from None
        except urllib.error.URLError as e:
            raise GlpiError(f"Cannot reach GLPI at {self.base}: {e.reason}") from None

    def login(self, user=None, password=None, user_token=None):
        if user_token:
            auth = {"Authorization": "user_token " + user_token}
        else:
            cred = base64.b64encode(f"{user}:{password}".encode()).decode()
            auth = {"Authorization": "Basic " + cred}
        data, _ = self._call("GET", "initSession", extra_headers=auth)
        self.headers["Session-Token"] = data["session_token"]

    def logout(self):
        try:
            self._call("GET", "killSession")
        except GlpiError:
            pass

    def all(self, itemtype):
        """Return every non-deleted object of an itemtype."""
        out, start, step = [], 0, 500
        while True:
            try:
                data, headers = self._call(
                    "GET", itemtype, query={"range": f"{start}-{start + step - 1}", "is_deleted": 0}
                )
            except GlpiError as e:
                if "ERROR_RANGE_EXCEED_TOTAL" in str(e):
                    break
                raise
            out.extend(data or [])
            total = int((headers.get("Content-Range") or "0-0/0").split("/")[-1])
            start += step
            if start >= total:
                break
        return out

    def add(self, itemtype, fields):
        data, _ = self._call("POST", itemtype, body={"input": fields})
        if isinstance(data, list):
            data = data[0]
        if not data or not data.get("id"):
            raise GlpiError(f"Could not create {itemtype}: {data}")
        return data["id"]

    def update(self, itemtype, item_id, fields):
        self._call("PUT", f"{itemtype}/{item_id}", body={"input": fields})


class Importer:
    def __init__(self, api, dry_run=False):
        self.api = api
        self.dry = dry_run
        self.cache = {}
        self.fake_id = -1
        self.errors = 0

    def log(self, msg):
        print(("[dry-run] " if self.dry else "") + msg)

    def index(self, itemtype):
        if itemtype not in self.cache:
            self.cache[itemtype] = {}
            for obj in self.api.all(itemtype):
                self.cache[itemtype].setdefault((obj.get("name") or "").strip().lower(), obj)
        return self.cache[itemtype]

    def model_by_id(self, itemtype, model_id):
        if not model_id:
            return None
        return next((m for m in self.index(itemtype + "Model").values() if m.get("id") == model_id), None)

    def ensure(self, itemtype, name, fields, update=True):
        """Find an object by name, creating or updating it. Returns its id."""
        idx = self.index(itemtype)
        obj = idx.get(name.strip().lower())
        if obj is None:
            self.log(f"+ create {itemtype} '{name}'")
            if self.dry:
                new_id = self.fake_id
                self.fake_id -= 1
            else:
                new_id = self.api.add(itemtype, dict(fields, name=name))
            idx[name.strip().lower()] = dict(fields, name=name, id=new_id)
            return new_id
        changes = {k: v for k, v in fields.items() if update and str(obj.get(k)) != str(v)}
        if changes:
            self.log(f"~ update {itemtype} '{name}': {changes}")
            if not self.dry and obj["id"] > 0:
                self.api.update(itemtype, obj["id"], changes)
            obj.update(changes)
        return obj["id"]

    # ---- racks.csv -------------------------------------------------------
    def import_racks(self, path):
        for row in read_csv(path):
            try:
                dc_id = self.ensure("Datacenter", row["datacenter"], {}, update=False)
                room_fields = {"datacenters_id": dc_id}
                if row.get("room_cols"):
                    room_fields["vis_cols"] = int(row["room_cols"])
                if row.get("room_rows"):
                    room_fields["vis_rows"] = int(row["room_rows"])
                room_id = self.ensure("DCRoom", row["room"], room_fields)

                rack_fields = {
                    "dcrooms_id": room_id,
                    "number_units": int(row.get("units") or 42),
                    "room_orientation": ORIENTATION[(row.get("orientation") or "N").strip().upper()[0]],
                }
                if row.get("col") and row.get("row"):
                    rack_fields["position"] = f"{int(row['col'])},{int(row['row'])}"
                for csv_key, glpi_key in (("max_power_w", "max_power"), ("max_weight_kg", "max_weight")):
                    if row.get(csv_key):
                        rack_fields[glpi_key] = int(row[csv_key])
                if row.get("model"):
                    rack_fields["rackmodels_id"] = self.ensure("RackModel", row["model"], {}, update=False)
                self.ensure("Rack", row["rack"], rack_fields)
            except (GlpiError, KeyError, ValueError) as e:
                self.fail(path, row, e)

    # ---- devices.csv -----------------------------------------------------
    def import_devices(self, path):
        racks = self.index("Rack")
        for row in read_csv(path):
            try:
                self.import_device(row, racks)
            except (GlpiError, KeyError, ValueError) as e:
                self.fail(path, row, e)

    def import_device(self, row, racks):
        name = row["name"].strip()
        dtype = row["type"].strip()
        itemtype = TYPE_ALIASES.get(dtype.lower().replace(" ", "").replace("_", ""), dtype)
        rack = racks.get(row["rack"].strip().lower())
        if rack is None:
            raise KeyError(f"rack '{row['rack']}' not found (add it to racks.csv first)")

        model_fk = itemtype.lower() + "models_id"
        model_fields = {}
        if row.get("units"):
            model_fields["required_units"] = int(row["units"])
        if row.get("power_w"):
            # PDU models store their capacity, other models their consumption
            power_key = "max_power" if itemtype == "PDU" else "power_consumption"
            model_fields[power_key] = int(row["power_w"])
        if row.get("weight_kg"):
            model_fields["weight"] = int(row["weight_kg"])
        if (row.get("half") or "").strip().lower() in ("left", "right"):
            model_fields["is_half_rack"] = 1

        item_fields = {}
        if row.get("serial"):
            item_fields["serial"] = row["serial"].strip()
        existing = self.index(itemtype).get(name.lower())
        current_model = self.model_by_id(itemtype, existing.get(model_fk)) if existing else None
        if row.get("model"):
            model_name = row["model"].strip()
            if current_model and current_model.get("name", "").strip().lower() != model_name.lower():
                self.log(f"  note: '{name}' has model '{current_model['name']}' from inventory; "
                         f"CSV sets '{model_name}' (the next agent run may switch it back)")
            item_fields[model_fk] = self.ensure(itemtype + "Model", model_name, model_fields)
        elif current_model and model_fields:
            # No model in the CSV: size the model the device already has (e.g. from inventory)
            self.ensure(itemtype + "Model", current_model["name"], model_fields)
        # Keep data that inventory already filled in; only set what the CSV provides
        item_id = self.ensure(itemtype, name, item_fields)

        position = int(row["u"])
        side = (row.get("face") or "front").strip().lower()
        if itemtype == "PDU" and side in PDU_SIDE:
            self.place("PDU_Rack", "pdus_id", item_id, rack["id"], name, {
                "pdus_id": item_id, "racks_id": rack["id"], "side": PDU_SIDE[side], "position": position,
            })
            return

        self.place("Item_Rack", None, item_id, rack["id"], name, {
            "itemtype": itemtype, "items_id": item_id, "racks_id": rack["id"],
            "position": position,
            "orientation": FACE[side],
            "hpos": HPOS[(row.get("half") or "").strip().lower()],
        })

    def place(self, linktype, fk, item_id, rack_id, name, fields):
        key = "_links_" + linktype
        if key not in self.cache:
            self.cache[key] = self.api.all(linktype)
        links = self.cache[key]
        if fk:
            existing = next((l for l in links if l.get(fk) == item_id), None)
        else:
            existing = next(
                (l for l in links if l.get("itemtype") == fields["itemtype"] and l.get("items_id") == item_id),
                None,
            )
        where = f"rack #{rack_id} U{fields['position']}"
        if existing is None:
            self.log(f"+ mount '{name}' in {where}")
            if not self.dry:
                fields_id = self.api.add(linktype, fields)
                links.append(dict(fields, id=fields_id))
        else:
            changes = {k: v for k, v in fields.items() if str(existing.get(k)) != str(v)}
            if changes:
                self.log(f"~ move '{name}' to {where}")
                if not self.dry:
                    self.api.update(linktype, existing["id"], changes)
                existing.update(changes)

    def fail(self, path, row, err):
        self.errors += 1
        print(f"! {path}: {dict(row)} -> {err}", file=sys.stderr)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if any(row.values()) and not next(iter(row.values())).startswith("#"):
                yield row


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", required=True, help="GLPI base URL, e.g. http://10.0.0.5")
    p.add_argument("--user", help="GLPI login (password from $GLPI_PASSWORD or prompt)")
    p.add_argument("--user-token", help="GLPI API user token instead of login/password")
    p.add_argument("--app-token", help="App-Token if your API client requires one")
    p.add_argument("--racks", help="racks.csv")
    p.add_argument("--devices", help="devices.csv")
    p.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    p.add_argument("--insecure", action="store_true", help="skip TLS certificate check (self-signed)")
    args = p.parse_args()

    if not (args.racks or args.devices):
        p.error("give --racks and/or --devices")
    if not (args.user or args.user_token):
        p.error("give --user or --user-token")

    api = Glpi(args.url, args.app_token, verify_ssl=not args.insecure)
    try:
        if args.user_token:
            api.login(user_token=args.user_token)
        else:
            password = os.environ.get("GLPI_PASSWORD") or getpass.getpass(f"GLPI password for {args.user}: ")
            api.login(args.user, password)
    except GlpiError as e:
        sys.exit(f"Login failed: {e}")

    imp = Importer(api, args.dry_run)
    try:
        if args.racks:
            imp.import_racks(args.racks)
        if args.devices:
            imp.import_devices(args.devices)
    finally:
        api.logout()

    if imp.errors:
        sys.exit(f"Finished with {imp.errors} error(s).")
    print("Done.")


if __name__ == "__main__":
    main()
