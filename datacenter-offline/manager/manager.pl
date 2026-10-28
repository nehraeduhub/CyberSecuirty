#!/usr/bin/perl
# DC NOC management API (/api/ on the portal): the device list (devices.json:
# what scans find plus what people add or edit), live up/down from Prometheus,
# settings (networks to scan, SNMP credentials, scan options, features),
# "Scan now", and the browser SSH terminal. No sign-in: keep the portal on the
# management network.
#
# Environment:
#   LISTEN          0.0.0.0:8090
#   PROMETHEUS_URL  http://prometheus:9090
#   SETTINGS_FILE   /settings/settings.json   (read by the collector and monitor-sync)
#   DEVICES_FILE    /settings/devices.json    (read by monitor-sync)
#   SCAN_REQUEST    /status/scan-request      (the collector starts a run when it appears)
#   SYNC_REQUEST    /settings/sync-request    (monitor-sync re-reads the devices when it appears)
#   DISCOVER_SCRIPT /opt/discover-networks.pl
#   SSH_KNOWN_HOSTS /settings/ssh_known_hosts.json
use strict;
use warnings;
use HTTP::Daemon;
use HTTP::Status qw(:constants);
use HTTP::Response;
use LWP::UserAgent;
use JSON::PP;
use URI::Escape qw(uri_escape uri_unescape);
use POSIX qw(strftime);
use Encode ();
use MIME::Base64 ();
use Digest::SHA qw(sha1);
use IO::Select;
use Socket qw(IPPROTO_TCP TCP_NODELAY);

my $listen   = $ENV{LISTEN} || '0.0.0.0:8090';
my $prom     = ($ENV{PROMETHEUS_URL} || 'http://prometheus:9090') =~ s{/+$}{}r;
my $file     = $ENV{SETTINGS_FILE} || '/settings/settings.json';
my $scan_req = $ENV{SCAN_REQUEST} || '/status/scan-request';
my $sync_req = $ENV{SYNC_REQUEST} || '/settings/sync-request';
my $discover = $ENV{DISCOVER_SCRIPT} || '/opt/discover-networks.pl';
my $dev_file = $ENV{DEVICES_FILE} || '/settings/devices.json';
my $known_hosts = $ENV{SSH_KNOWN_HOSTS} || '/settings/ssh_known_hosts.json';

my $json = JSON::PP->new->utf8->canonical->pretty;
my $ua   = LWP::UserAgent->new(timeout => 20, agent => 'dc-manager');
my $MASK = '********';
$| = 1;

sub logmsg { printf "%s %s\n", strftime('%F %T', localtime), join('', @_) }

# ------------------------------------------------------------------ settings
# Defaults for a fresh install: the Monitor, device list and network scanning;
# the extras can be switched on from the Scan & settings page.
sub defaults {
    return {
        networks => [],
        snmp     => [],
        scan     => { interval_minutes => 60, threads => 32, timeout => 2 },
        features => {
            grafana => JSON::PP::false, library => JSON::PP::true,
            servers => JSON::PP::false, vmware => JSON::PP::false,
        },
    };
}

sub load_settings {
    my $d = defaults();
    open my $fh, '<', $file or return $d;
    local $/; my $raw = <$fh>; close $fh;
    my $s = eval { decode_json($raw) } or return $d;
    for my $k (keys %$d) { $s->{$k} //= $d->{$k} }
    for my $k (keys %{ $d->{features} }) { $s->{features}{$k} //= $d->{features}{$k} }
    delete $s->{features}{$_} for grep { !exists $d->{features}{$_} } keys %{ $s->{features} };
    delete $s->{categories};
    for my $k (keys %{ $d->{scan} }) { $s->{scan}{$k} //= $d->{scan}{$k} }
    return $s;
}

sub save_settings {
    my ($s) = @_;
    my $tmp = "$file.tmp";
    open my $fh, '>', $tmp or die "write $tmp: $!\n";
    chmod 0600, $tmp;
    print $fh $json->encode($s);
    close $fh;
    rename $tmp, $file or die "rename $tmp: $!\n";
}

sub touch { my $f = shift; open my $fh, '>', $f or return 0; print $fh time, "\n"; close $fh; 1 }

my @SECRETS = qw(community authpassword privpassword);

sub masked {
    my ($s) = @_;
    my $c = decode_json(encode_json($s));
    for my $cr (@{ $c->{snmp} }) { $cr->{$_} = $MASK for grep { defined $cr->{$_} && length $cr->{$_} } @SECRETS }
    return $c;
}

sub is_ipv4 { my $ip = shift // ''; $ip =~ /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/ && !grep { $_ > 255 } ($1, $2, $3, $4) }

# "10.1.2.0/24", "10.1.2.10-10.1.2.50" or "10.1.2.7" -> normalised string, or error
sub check_network {
    my ($n) = @_;
    $n =~ s/\s+//g;
    if ($n =~ m{^([\d.]+)/(\d+)$}) {
        return (undef, "$n: not an IPv4 network") unless is_ipv4($1) && $2 <= 32;
        return (undef, "$n is too large (more than 65,536 addresses); split it into /16 or smaller") if $2 < 16;
        my $m = $2 ? (0xFFFFFFFF << (32 - $2)) & 0xFFFFFFFF : 0;
        my $net = join '.', unpack 'C4', pack 'N', (unpack('N', pack 'C4', split /\./, $1) & $m);
        return ("$net/$2");
    }
    if ($n =~ /^([\d.]+)-([\d.]+)$/) {
        return (undef, "$n: not an IPv4 range") unless is_ipv4($1) && is_ipv4($2);
        my ($a, $b) = map { unpack 'N', pack 'C4', split /\./ } ($1, $2);
        return (undef, "$n: the first address is after the last") if $a > $b;
        return (undef, "$n is too large (more than 65,536 addresses)") if $b - $a > 65535;
        return ($n);
    }
    return ($n) if is_ipv4($n);
    return (undef, "'$n' is not a network (use 192.168.15.0/24, 192.168.15.10-192.168.15.50 or one IP)");
}

# Validate a settings document from the browser; keep stored secrets where the
# browser sent the mask back.
sub merge_settings {
    my ($old, $new) = @_;
    my $s = defaults();
    my @err;
    my %seen;
    for my $n (@{ $new->{networks} || [] }) {
        my ($net, $e) = check_network($n->{network} // '');
        if ($e) { push @err, $e; next }
        next if $seen{$net}++;
        push @{ $s->{networks} }, {
            network => $net, name => substr($n->{name} // '', 0, 80),
            enabled => $n->{enabled} ? JSON::PP::true : JSON::PP::false,
        };
    }
    my %oldcred = map { ($_->{id} // '') => $_ } @{ $old->{snmp} || [] };
    my $i = 0;
    for my $c (@{ $new->{snmp} || [] }) {
        $i++;
        my $v = $c->{version} // '2c';
        unless ($v =~ /^(1|2c|3)$/) { push @err, "SNMP credential $i: version must be 1, 2c or 3"; next }
        my $prev = $oldcred{ $c->{id} // '' } || {};
        my %o = (id => ($c->{id} && $c->{id} =~ /^[\w-]{1,40}$/ ? $c->{id} : sprintf('c%d%04d', time, int rand 10000)),
                 version => $v, name => substr($c->{name} // '', 0, 80),
                 enabled => $c->{enabled} ? JSON::PP::true : JSON::PP::false);
        for my $k (qw(community username authprotocol authpassword privprotocol privpassword)) {
            my $val = $c->{$k} // '';
            $val = $prev->{$k} // '' if $val eq $MASK;
            # No commas, spaces or quotes: the agent's credential syntax can't carry them
            if ($val =~ /[,\s"'`\\]/) { push @err, "SNMP credential $i: $k may not contain spaces, commas, quotes or backslashes"; next }
            $o{$k} = $val if length $val;
        }
        if ($v eq '3') {
            push @err, "SNMP credential $i: SNMPv3 needs a user name" unless $o{username};
            for (qw(authpassword privpassword)) {
                push @err, "SNMP credential $i: the $_ must have at least 8 characters" if $o{$_} && length $o{$_} < 8;
            }
            $o{authprotocol} = lc($o{authprotocol} || 'sha') if $o{authpassword};
            $o{privprotocol} = lc($o{privprotocol} || 'aes') if $o{privpassword};
            push @err, "SNMP credential $i: authentication must be md5 or sha" if $o{authprotocol} && $o{authprotocol} !~ /^(md5|sha)$/;
            push @err, "SNMP credential $i: privacy must be des, 3des or aes" if $o{privprotocol} && $o{privprotocol} !~ /^(des|3des|aes)$/;
            push @err, "SNMP credential $i: privacy needs an authentication password too" if $o{privpassword} && !$o{authpassword};
        } else {
            push @err, "SNMP credential $i: community is empty" unless $o{community};
            delete @o{qw(username authprotocol authpassword privprotocol privpassword)};
        }
        push @{ $s->{snmp} }, \%o;
    }
    my $sc = $new->{scan} || {};
    my %lim = (interval_minutes => [5, 10080], threads => [1, 128], timeout => [1, 30]);
    for my $k (keys %lim) {
        my $v = $sc->{$k} // $s->{scan}{$k};
        if ($v !~ /^\d+$/ || $v < $lim{$k}[0] || $v > $lim{$k}[1]) { push @err, "$k must be $lim{$k}[0]-$lim{$k}[1]"; next }
        $s->{scan}{$k} = $v + 0;
    }
    for my $k (keys %{ $s->{features} }) {
        $s->{features}{$k} = ($new->{features} || {})->{$k} ? JSON::PP::true : JSON::PP::false
            if exists(($new->{features} || {})->{$k});
    }
    return ($s, \@err);
}

# ------------------------------------------------------------------ status
sub prom_query {
    my ($q) = @_;
    my $r = $ua->get("$prom/api/v1/query?query=" . uri_escape($q));
    return [] unless $r->is_success;
    my $d = eval { decode_json($r->decoded_content) } or return [];
    return $d->{data}{result} || [];
}

# ip -> { up, rtt_ms } for every device monitor-sync pings
sub device_status {
    my %out;
    for my $m (@{ prom_query('max by (instance) (probe_success{job="device"})') }) {
        $out{ $m->{metric}{instance} }{up} = $m->{value}[1] eq '1' ? JSON::PP::true : JSON::PP::false;
    }
    for my $m (@{ prom_query('max by (instance) (probe_icmp_duration_seconds{job="device",phase="rtt"})') }) {
        next unless $out{ $m->{metric}{instance} } && $out{ $m->{metric}{instance} }{up};
        $out{ $m->{metric}{instance} }{rtt_ms} = sprintf('%.1f', $m->{value}[1] * 1000) + 0;
    }
    return \%out;
}

# ------------------------------------------------------------------ devices
# Categories on the Monitor page, in display order
my @CATEGORIES = ('Firewall', 'Load balancer', 'Router', 'Switch', 'Wireless', 'Server', 'Storage',
                  'Management', 'Power', 'Printer', 'Phone', 'Other', 'Unknown');
my %IS_CATEGORY = map { $_ => 1 } @CATEGORIES;
# Fields people can edit; an edited field is never overwritten by a scan
my @EDITABLE = qw(name ip category brand model serial mac location notes);

# Best guess from what a scan found; people can override it per device
sub auto_category {
    my ($d) = @_;
    # (reading through map { $d->{$_} } so no empty keys are added to the device)
    my $t = lc join ' ', map { $d->{$_} // '' } qw(brand model type description name);
    return 'Management' if $t =~ /integrated lights|\bilo\b|idrac|\bimm\b|\bbmc\b|\bxcc\b|ipmi/;
    return 'Power'    if $t =~ /\b(ups|pdu|apc|eaton|vertiv|liebert|smart-ups|rack pdu)\b/;
    return 'Firewall' if $t =~ /firewall|sophos|fortinet|fortigate|palo ?alto|check ?point|firepower|\basa\b|watchguard|sonicwall|pfsense|opnsense|juniper srx|\bsrx\d/;
    return 'Load balancer' if $t =~ /load ?balanc|radware|alteon|\bf5\b|big-?ip|netscaler|citrix adc|\ba10\b|kemp|array networks|\bslb\b|\badc\b/;
    return 'Storage'  if $t =~ /storage|\bnas\b|\bsan\b|3par|primera|nimble|\bmsa\b|powervault|powerstore|netapp|unity|synology|qnap|simplivity|isilon/;
    return 'Wireless' if $t =~ /wireless|\bwlc\b|aironet|access point|\bap\d|ruckus|ubiquiti|unifi|meraki mr|instant on ap/;
    return 'Router'   if $t =~ /router|\bisr\d*\b|\basr\d*\b|\bcsr\d*|\bmx\d|vyos|mikrotik|edgerouter|\bc8\d{2}0|catalyst 8\d00/;
    return 'Printer'  if ($d->{type} // '') eq 'PRINTER' || $t =~ /printer|laserjet|officejet/;
    return 'Phone'    if ($d->{type} // '') eq 'PHONE';
    return 'Server'   if ($d->{type} // '') eq 'COMPUTER' || $t =~ /proliant|poweredge|server|esxi|vmware|linux|windows/;
    return 'Switch'   if ($d->{type} // '') eq 'NETWORKING' || $t =~ /switch|catalyst|nexus|procurve|aruba|os10|comware/;
    return $d->{snmp} ? 'Other' : 'Unknown';
}

sub ipnum { my $ip = shift // ''; $ip =~ /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/ ? (($1 * 256 + $2) * 256 + $3) * 256 + $4 : 2**33 }
sub now_iso { strftime('%Y-%m-%dT%H:%M:%SZ', gmtime) }

sub clean {   # one line of text, no control characters, at most $max characters
    my ($v, $max) = @_;
    $v = '' unless defined $v;
    $v =~ s/[\x00-\x1f\x7f]+/ /g;
    $v =~ s/^\s+|\s+$//g;
    return substr($v, 0, $max || 200);
}
# Text some devices send UTF-8-encoded twice ("â€”" for "—"): undo it
sub fix_text {
    my $v = shift;
    for (1 .. 3) {
        last unless $v =~ /[\xC2-\xF4][\x80-\xBF]/ && $v !~ /[^\x00-\xFF]/;
        my $t = eval { Encode::decode('UTF-8', Encode::encode('latin1', $v), Encode::FB_CROAK()) };
        last unless defined $t;
        $v = $t;
    }
    return $v;
}
sub clean_mac {
    my $m = lc clean(shift, 40);
    $m =~ s/-/:/g;
    return $m =~ /^([0-9a-f]{2}:){5}[0-9a-f]{2}$/ && $m ne '00:00:00:00:00:00' ? $m : '';
}

sub load_devices {
    open my $fh, '<', $dev_file or return { devices => [], next_id => 1 };
    local $/; my $d = eval { decode_json(<$fh>) };
    close $fh;
    return ref $d eq 'HASH' && ref $d->{devices} eq 'ARRAY' ? $d : { devices => [], next_id => 1 };
}
sub save_devices {
    my ($db) = @_;
    @{ $db->{devices} } = sort { ipnum($a->{ip}) <=> ipnum($b->{ip}) } @{ $db->{devices} };
    open my $fh, '>', "$dev_file.tmp" or die "write $dev_file.tmp: $!\n";
    print $fh $json->encode($db);
    close $fh;
    rename "$dev_file.tmp", $dev_file or die "rename $dev_file: $!\n";
    touch($sync_req);   # monitor-sync picks the change up right away
}

# Set fields from people's input; returns error text or ''
sub apply_edit {
    my ($db, $d, $in) = @_;
    for my $k (@EDITABLE) {
        next unless exists $in->{$k};
        my $v = $k eq 'notes' ? clean($in->{$k}, 2000) : clean($in->{$k});
        if ($k eq 'ip') {
            return "'$v' is not an IPv4 address" unless is_ipv4($v);
            return "$v is already used by another device" if grep { $_->{ip} eq $v && $_ != $d } @{ $db->{devices} };
        }
        if ($k eq 'mac' && length $v) { my $m = clean_mac($v) or return "'$v' is not a MAC address"; $v = $m }
        if ($k eq 'category') {
            return "Unknown category '$v'" if length $v && !$IS_CATEGORY{$v};
            if (!length $v) { delete $d->{locked}{category}; $d->{category} = auto_category($d); next }   # back to automatic
        }
        $d->{$k} = $v;
        $d->{locked}{$k} = JSON::PP::true;
    }
    $d->{name} = $d->{ip} unless length($d->{name} // '');
    $d->{category} = auto_category($d) unless $d->{locked}{category};
    return '';
}

# Names SNMP reports for older product lines
sub brand_name {
    my ($b, $model) = @_;
    return 'Hewlett Packard Enterprise' if $b =~ /^compaq/i;                   # iLO
    return 'Radware' if $b =~ /^nortel|^alteon/i || $model =~ /alteon|^aws\d/i;  # Alteon
    return 'Hewlett Packard Enterprise' if $b =~ /^hewlett.packard enterprise|^hpe$/i;
    return $b;
}

# Results of a scan, from the collector: add new devices, refresh found facts,
# but never overwrite what people edited
sub import_devices {
    my ($list, $source) = @_;
    my $db = load_devices();
    my %by = map { $_->{ip} => $_ } @{ $db->{devices} };
    my ($new, $upd) = (0, 0);
    for my $f (@$list) {
        my $ip = $f->{ip} // '';
        next unless is_ipv4($ip);
        my $d = $by{$ip};
        # Same serial number as a known device at another address: the same box
        # (e.g. a switch with several IPs), so keep one entry and note the address
        my $serial = clean($f->{serial}, 80);
        if (!$d && length $serial >= 4) {
            my ($twin) = grep { ($_->{serial} // '') eq $serial } @{ $db->{devices} };
            if ($twin) {
                my %ips = map { $_ => 1 } @{ $twin->{other_ips} || [] };
                $ips{$ip} = 1;
                $twin->{other_ips} = [ sort keys %ips ];
                $upd++;
                next;
            }
        }
        unless ($d) {
            $d = $by{$ip} = { id => $db->{next_id}++, ip => $ip, name => $ip, source => $source || 'scan',
                              first_seen => now_iso(), locked => {} };
            push @{ $db->{devices} }, $d;
            $new++;
        } else { $upd++ }
        $f->{$_} = fix_text($f->{$_}) for grep { defined $f->{$_} && !ref $f->{$_} } keys %$f;
        my %facts = (brand => brand_name(clean($f->{manufacturer}), clean($f->{model})), model => clean($f->{model}), serial => clean($f->{serial}, 80),
                     mac => clean_mac($f->{mac}), location => clean($f->{location}), type => clean($f->{type}, 40),
                     description => clean($f->{description}, 300), firmware => clean($f->{firmware}, 120));
        for my $k (keys %facts) {
            next if $d->{locked}{$k} || !length $facts{$k};
            $d->{$k} = $facts{$k};
        }
        my $sysname = clean($f->{name}, 120);
        $d->{name} = $sysname if !$d->{locked}{name} && length $sysname && $d->{name} eq $d->{ip};
        $d->{snmp} = JSON::PP::true if $f->{snmp};
        $d->{last_seen} = now_iso();
        $d->{category} = auto_category($d) unless $d->{locked}{category};
    }
    save_devices($db) if $new || $upd;
    logmsg("import from $source: $new new, $upd updated device(s)") if $new || $upd;
    return { added => $new, updated => $upd };
}

# Everything the Monitor page shows, in one call
sub monitor {
    my $db  = load_devices();
    my $st  = device_status();
    my %last_up;
    for my $m (@{ prom_query('time() - max by (instance) (max_over_time((timestamp(probe_success{job="device"} == 1))[24h:30s]))') }) {
        $last_up{ $m->{metric}{instance} } = int $m->{value}[1];
    }
    my (%cat, @out);
    my %tot = (total => 0, up => 0, down => 0, unknown => 0);
    for my $d (@{ $db->{devices} }) {
        my %o = map { $_ => $d->{$_} } qw(id ip name category brand model serial mac location);
        $o{category} = 'Unknown' unless $IS_CATEGORY{ $o{category} // '' };
        my $x = $st->{ $d->{ip} };
        $o{state} = !$x ? 'unknown' : $x->{up} ? 'up' : 'down';
        $o{rtt_ms} = $x->{rtt_ms} if $x && defined $x->{rtt_ms};
        # Down: seconds since the last good ping (absent = not up in the last 24 h)
        $o{down_for_s} = $last_up{ $d->{ip} } if $o{state} eq 'down' && defined $last_up{ $d->{ip} };
        my $c = $cat{ $o{category} } //= { name => $o{category}, total => 0, up => 0, down => 0, unknown => 0 };
        $c->{total}++; $c->{ $o{state} }++;
        $tot{total}++; $tot{ $o{state} }++;
        push @out, \%o;
    }
    return {
        generated  => time,
        totals     => \%tot,
        categories => [ map { $cat{$_} } grep { $cat{$_} } @CATEGORIES ],
        category_list => \@CATEGORIES,
        devices    => \@out,
    };
}

# ------------------------------------------------------------- find networks
sub cred_line {
    my ($c) = @_;
    my @p = ("version:$c->{version}");
    for my $k (qw(community username authprotocol authpassword privprotocol privpassword)) {
        push @p, "$k:$c->{$k}" if defined $c->{$k} && length $c->{$k};
    }
    return join ',', @p;
}

sub find_networks {
    my ($router, $s) = @_;
    my @creds = map { cred_line($_) } grep { $_->{enabled} } @{ $s->{snmp} };
    return { error => 'Add an SNMP credential first: the router is asked over SNMP.' } unless @creds;
    open my $fh, '-|', 'perl', $discover, join(';', @creds), $router
        or return { error => "Cannot run the network finder: $!" };
    my @nets;
    while (my $l = <$fh>) {
        chomp $l;
        my ($net, undef, $src) = split /\t/, $l;
        push @nets, { network => $net, source => $src } if $net;
    }
    close $fh;
    return { networks => \@nets, error => @nets ? undef : "No answer from $router with your SNMP credentials, or it has no IPv4 networks" };
}

# ------------------------------------------------------------- web SSH
# The DC Viewer's SSH terminal (ssh.html, xterm.js) talks to this over a
# WebSocket; each session runs in its own process. Only devices in the device
# list can be reached. Host keys are
# trusted on first use and checked every time after.

sub ws_send {
    my ($sock, $op, $data) = @_;
    my $len = length $data;
    my $h = chr(0x80 | $op);
    $h .= $len < 126 ? chr($len) : $len < 65536 ? chr(126) . pack('n', $len) : chr(127) . pack('Q>', $len);
    my $buf = $h . $data;
    while (length $buf) {
        my $n = syswrite($sock, $buf);
        return 0 unless defined $n;
        substr($buf, 0, $n, '');
    }
    return 1;
}
sub ws_json { ws_send($_[0], 1, encode_json($_[1])) }

# Complete frames from $$buf: list of [opcode, payload]
sub ws_frames {
    my ($buf) = @_;
    my @out;
    while (length $$buf >= 2) {
        my ($b1, $b2) = unpack 'CC', $$buf;
        my $len = $b2 & 0x7f;
        my $off = 2;
        if ($len == 126) { return @out if length $$buf < 4; $len = unpack 'n', substr($$buf, 2, 2); $off = 4 }
        elsif ($len == 127) { return @out if length $$buf < 10; $len = unpack 'Q>', substr($$buf, 2, 8); $off = 10 }
        die "frame too large\n" if $len > 1 << 20;
        my $mask = '';
        if ($b2 & 0x80) { return @out if length $$buf < $off + 4; $mask = substr($$buf, $off, 4); $off += 4 }
        return @out if length $$buf < $off + $len;
        my $data = substr($$buf, $off, $len);
        substr($$buf, 0, $off + $len, '');
        $data ^= substr($mask x (int($len / 4) + 1), 0, $len) if length $mask;
        push @out, [ $b1 & 0x0f, $data ];
    }
    return @out;
}

sub load_known { open my $fh, '<', $known_hosts or return {}; local $/; my $d = eval { decode_json(<$fh>) }; ref $d eq 'HASH' ? $d : {} }
sub save_known {
    my $k = shift;
    open my $fh, '>', "$known_hosts.tmp" or return;
    print $fh $json->encode($k);
    close $fh;
    rename "$known_hosts.tmp", $known_hosts;
}

sub ssh_session {
    my ($sock, $ip, $port, $who) = @_;
    require Net::SSH2;
    my $sel = IO::Select->new($sock);
    my $in = '';
    my $next_msg = sub {   # wait for the next JSON message from the browser
        my $deadline = time + 300;
        while (time < $deadline) {
            for my $f (ws_frames(\$in)) {
                return undef if $f->[0] == 8;
                ws_send($sock, 10, $f->[1]) if $f->[0] == 9;
                return eval { decode_json($f->[1]) } if $f->[0] == 1;
            }
            next unless $sel->can_read(1);
            my $n = sysread($sock, $in, 65536, length $in);
            return undef unless $n;
        }
        return undef;
    };
    my $fail = sub { ws_json($sock, { type => 'error', text => shift }); ws_send($sock, 8, ''); return };

    ws_json($sock, { type => 'status', text => "Connecting to $ip:$port…" });
    my $ssh = Net::SSH2->new(timeout => 15000);
    $ssh->connect($ip, $port) or return $fail->("Cannot connect to $ip port $port: " . ($ssh->error)[2]);
    # Fingerprint as OpenSSH shows it: SHA256 of the host key blob, base64 without padding
    my ($blob) = $ssh->remote_hostkey;
    return $fail->("$ip did not present an SSH host key") unless defined $blob && length $blob;
    my $fp = 'SHA256:' . (MIME::Base64::encode_base64(Digest::SHA::sha256($blob), '') =~ s/=+$//r);
    my $known = load_known();
    my $was = $known->{"$ip:$port"};
    my $state = !$was ? 'new' : $was eq $fp ? 'known' : 'changed';
    ws_json($sock, { type => 'hostkey', fingerprint => $fp, state => $state });
    if ($state eq 'changed') {
        logmsg("ssh: host key of $ip:$port CHANGED (was $was, now $fp) - refused for $who->{name}");
        return $fail->("The SSH host key of $ip changed since the first connection. This can mean the device was replaced or reinstalled - or that someone is intercepting the connection. Check with the device owner; then remove the old key under Scan & settings > SSH host keys.");
    }
    my $login = $next_msg->() or return;
    return $fail->('Expected a login') unless ($login->{type} // '') eq 'login' && length($login->{user} // '');
    if ($state eq 'new') {
        return $fail->('Host key not accepted') unless $login->{trust};
        $known = load_known();
        $known->{"$ip:$port"} = $fp;
        save_known($known);
    }
    my ($user, $pass) = ($login->{user}, $login->{password} // '');
    my $ok = $ssh->auth_password($user, $pass)
        || $ssh->auth_keyboard($user, $pass);
    logmsg("ssh: $who->{name} -> $user\@$ip:$port ", $ok ? 'logged in' : 'login failed');
    return $fail->('Login failed: wrong user name or password, or password login is disabled on the device.') unless $ok;
    my $ch = $ssh->channel or return $fail->('Cannot open a session channel');
    my ($cols, $rows) = map { ($login->{$_} // 0) =~ /^\d{1,4}$/ ? $login->{$_} : 0 } qw(cols rows);
    $ch->pty('xterm-256color', undef, $cols || 120, $rows || 32);
    $ch->shell or return $fail->('The device refused to start a shell');
    ws_json($sock, { type => 'ready' });
    $ssh->blocking(0);
    my $ssh_sock = $ssh->sock;
    $sel->add($ssh_sock);
    my $last = time;
    while (1) {
        my $buf;
        while (1) {   # drain what the device sent
            my $n = $ch->read($buf, 32768);
            last unless defined $n && $n > 0;
            ws_send($sock, 2, $buf) or return;
            $last = time;
        }
        my $e = $ch->read($buf, 32768, 1);   # stderr
        ws_send($sock, 2, $buf) if defined $e && $e > 0;
        if ($ch->eof) { ws_json($sock, { type => 'closed', text => 'Session ended' }); ws_send($sock, 8, ''); last }
        my @r = $sel->can_read(0.5);
        last if time - $last > 3600;      # 1 hour without any traffic
        next unless grep { $_ == $sock } @r;
        my $n2 = sysread($sock, $in, 65536, length $in);
        last unless $n2;
        for my $f (ws_frames(\$in)) {
            if ($f->[0] == 8) { $ch->close; return }
            if ($f->[0] == 9) { ws_send($sock, 10, $f->[1]); next }
            next unless $f->[0] == 1;
            my $m = eval { decode_json($f->[1]) } or next;
            $last = time;
            if (($m->{type} // '') eq 'data') {
                my $d = Encode::encode('UTF-8', $m->{data} // '');
                while (length $d) {
                    my $w = $ch->write($d);
                    if (defined $w && $w > 0) { substr($d, 0, $w, '') } else { select undef, undef, undef, 0.01 }
                }
            } elsif (($m->{type} // '') eq 'resize' && ($m->{cols} // '') =~ /^\d{1,4}$/ && ($m->{rows} // '') =~ /^\d{1,4}$/) {
                $ch->pty_size($m->{cols}, $m->{rows});
            }
        }
    }
    $ch->close;
    $ssh->disconnect;
}

# GET /api/ssh?host=IP&port=22&token=… with "Upgrade: websocket"
sub ssh_upgrade {
    my ($c, $req) = @_;
    my $who = { name => $req->header('X-Real-IP') || 'browser' };
    my %q = map { my ($k, $v) = split /=/, $_, 2; ($k => URI::Escape::uri_unescape($v // '')) } split /&/, ($req->uri->query // '');
    my ($ip, $port) = ($q{host} // '', $q{port} || 22);
    return reply($c, 400, { error => 'Bad host or port' }) unless is_ipv4($ip) && $port =~ /^\d{1,5}$/ && $port < 65536;
    return reply($c, 403, { error => "$ip is not in the device list" }) unless grep { $_->{ip} eq $ip } @{ load_devices()->{devices} };
    my $key = $req->header('Sec-WebSocket-Key') or return reply($c, 400, { error => 'Not a WebSocket request' });
    my $pid = fork;
    return logmsg("fork failed: $!") unless defined $pid;
    return if $pid;   # parent: back to serving the API
    # Child: this connection only
    $SIG{CHLD} = 'DEFAULT';
    my $accept = MIME::Base64::encode_base64(sha1($key . '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'), '');
    syswrite($c, "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: $accept\r\n\r\n");
    setsockopt($c, IPPROTO_TCP, TCP_NODELAY, 1);
    eval { ssh_session($c, $ip, $port, $who); 1 } or do {
        logmsg("ssh error: $@");
        eval { ws_json($c, { type => 'error', text => 'The SSH session failed on the server (see: docker compose logs manager).' }) };
    };
    close $c;
    POSIX::_exit(0);
}

# ------------------------------------------------------------------ server
sub reply {
    my ($c, $code, $data) = @_;
    my $r = HTTP::Response->new($code);
    $r->header('Content-Type' => 'application/json; charset=utf-8', 'Cache-Control' => 'no-store');
    $r->content($json->encode($data));
    $c->send_response($r);
}

sub body {
    my ($req) = @_;
    my $d = eval { decode_json($req->content || '{}') };
    return ref $d eq 'HASH' ? $d : undef;
}

sub handle {
    my ($c, $req) = @_;
    my $path = $req->uri->path =~ s{^/api}{}r;
    my $m = $req->method;
    my $from = $req->header('X-Real-IP') || 'browser';

    if ($m eq 'GET' && $path eq '/ssh' && lc($req->header('Upgrade') // '') eq 'websocket') {
        ssh_upgrade($c, $req);
        return;
    }
    return reply($c, 200, load_settings()->{features}) if $m eq 'GET' && $path eq '/features';
    return reply($c, 200, monitor()) if $m eq 'GET' && $path eq '/monitor';
    return reply($c, 200, device_status()) if $m eq 'GET' && $path eq '/status';
    return reply($c, 200, masked(load_settings())) if $m eq 'GET' && $path eq '/settings';

    # Devices
    if ($m eq 'GET' && $path eq '/devices') {
        return reply($c, 200, { devices => load_devices()->{devices}, category_list => \@CATEGORIES, editable => \@EDITABLE });
    }
    if ($m eq 'POST' && $path eq '/devices') {   # add by hand: { devices: [ {ip, name, category, …} ] }
        my $b = body($req) || {};
        my $db = load_devices();
        my (@err, @added);
        for my $in (@{ ref $b->{devices} eq 'ARRAY' ? $b->{devices} : [] }) {
            my $ip = clean($in->{ip});
            if (!is_ipv4($ip)) { push @err, "'$ip' is not an IPv4 address"; next }
            if (grep { $_->{ip} eq $ip } @{ $db->{devices} }) { push @err, "$ip is already in the list"; next }
            my $d = { id => $db->{next_id}++, ip => $ip, name => $ip, source => 'manual', first_seen => now_iso(), locked => {} };
            my %in = %$in; delete $in{ip};
            $in{category} = '' unless defined $in{category};
            if (my $e = apply_edit($db, $d, \%in)) { push @err, "$ip: $e"; next }
            push @{ $db->{devices} }, $d;
            push @added, $d;
        }
        save_devices($db) if @added;
        logmsg("$from added ", scalar @added, " device(s)") if @added;
        return reply($c, @err && !@added ? 400 : 200, { added => \@added, error => @err ? join("\n", @err) : undef });
    }
    if ($m eq 'PUT' && $path =~ m{^/devices/(\d+)$}) {
        my $id = $1;
        my $in = body($req) or return reply($c, 400, { error => 'Body must be a JSON object' });
        my $db = load_devices();
        my ($d) = grep { $_->{id} == $id } @{ $db->{devices} } or return reply($c, 404, { error => 'No such device' });
        my $e = apply_edit($db, $d, $in);
        return reply($c, 400, { error => $e }) if $e;
        save_devices($db);
        logmsg("$from edited device $id ($d->{ip})");
        return reply($c, 200, $d);
    }
    if ($m eq 'POST' && $path eq '/devices/bulk') {   # { ids: [..], category: '…' } or { ids: [..], delete: true }
        my $b = body($req) || {};
        my %ids = map { $_ => 1 } grep { /^\d+$/ } @{ ref $b->{ids} eq 'ARRAY' ? $b->{ids} : [] };
        return reply($c, 400, { error => 'Select devices first' }) unless %ids;
        my $db = load_devices();
        if ($b->{delete}) {
            my $before = @{ $db->{devices} };
            @{ $db->{devices} } = grep { !$ids{ $_->{id} } } @{ $db->{devices} };
            save_devices($db);
            logmsg("$from deleted ", $before - @{ $db->{devices} }, " device(s)");
            return reply($c, 200, { deleted => $before - @{ $db->{devices} } });
        }
        my $n = 0;
        for my $d (grep { $ids{ $_->{id} } } @{ $db->{devices} }) {
            my $e = apply_edit($db, $d, { category => $b->{category} // '' });
            return reply($c, 400, { error => $e }) if $e;
            $n++;
        }
        save_devices($db);
        return reply($c, 200, { updated => $n });
    }
    if ($m eq 'POST' && $path eq '/import') {   # from the collector
        my $b = body($req) || {};
        return reply($c, 200, import_devices(ref $b->{devices} eq 'ARRAY' ? $b->{devices} : [], clean($b->{source}, 60) || 'scan'));
    }

    # Settings and actions
    if ($m eq 'PUT' && $path eq '/settings') {
        my $new = body($req) or return reply($c, 400, { error => 'Body must be a JSON object' });
        my ($s, $err) = merge_settings(load_settings(), $new);
        return reply($c, 400, { error => join("\n", @$err) }) if @$err;
        save_settings($s);
        touch($sync_req);
        logmsg("$from saved settings: ", scalar @{ $s->{networks} }, " network(s), ", scalar @{ $s->{snmp} }, " credential(s)");
        return reply($c, 200, masked($s));
    }
    if ($m eq 'POST' && $path eq '/sync') { touch($sync_req); return reply($c, 202, { ok => 1 }) }
    if ($m eq 'POST' && $path eq '/scan') {
        touch($scan_req) or return reply($c, 500, { error => "Cannot write $scan_req" });
        logmsg("$from requested a scan");
        return reply($c, 202, { ok => 1 });
    }
    if ($m eq 'POST' && $path eq '/find-networks') {
        my $b = body($req) || {};
        return reply($c, 400, { error => 'Give the IP address of a router, L3 switch or firewall' }) unless is_ipv4($b->{router});
        return reply($c, 200, find_networks($b->{router}, load_settings()));
    }
    if ($m eq 'GET' && $path eq '/ssh-keys') { return reply($c, 200, load_known()) }
    if ($m eq 'DELETE' && $path =~ m{^/ssh-keys/([\d.]+:\d+)$}) {
        my $k = load_known();
        delete $k->{$1};
        save_known($k);
        logmsg("$from removed the SSH host key of $1");
        return reply($c, 200, { ok => 1 });
    }
    return reply($c, 404, { error => "No such API: $m $path" });
}

my ($host, $port) = split /:/, $listen;
my $d = HTTP::Daemon->new(LocalAddr => $host, LocalPort => $port, ReuseAddr => 1, Timeout => 30)
    or die "Cannot listen on $listen: $!\n";
save_settings(load_settings()) unless -e $file;
{   # Devices copied from GLPI or added by older versions: give each a category
    my $db = load_devices();
    my $changed = 0;
    for my $d (@{ $db->{devices} }) {
        $d->{locked} ||= {};
        my @empty = grep { !defined $d->{$_} } keys %$d;   # left by an older version
        if (@empty) { delete @$d{@empty}; $changed++ }
        next if $IS_CATEGORY{ $d->{category} // '' };
        $d->{category} = auto_category($d);
        $changed++;
    }
    save_devices($db) if $changed || !-e $dev_file;
}
logmsg("DC manager API on $listen, settings in $file");
$SIG{CHLD} = 'IGNORE';   # SSH session processes clean up after themselves
while (1) {
    my $c = $d->accept or next;
    $c->timeout(30);
    while (my $req = $c->get_request) {
        eval { handle($c, $req); 1 } or do { logmsg("error: $@"); reply($c, 500, { error => 'Internal error, see: docker compose logs manager' }) };
        last;   # one request per connection keeps this single-threaded server responsive
    }
    $c->close;
}
