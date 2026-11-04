/* Tech Guardians — tiny dependency-free Markdown renderer.
   Handles the features this kit uses: headings, hr, blockquotes, fenced code,
   tables, ordered/unordered lists, paragraphs, images, links, bold, italic,
   inline code. No external libraries, no network calls — safe for live hosting.
   Content rendered is the kit's OWN trusted Markdown. */
(function (global) {
  "use strict";

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // resolve "a/b/../c" and join base + rel
  function joinPath(base, rel) {
    if (/^([a-z]+:)?\/\//i.test(rel) || rel.startsWith("/") ||
        rel.startsWith("#") || rel.startsWith("mailto:") || rel.startsWith("tel:")) return rel;
    var parts = (base ? base.split("/") : []);
    rel.split("/").forEach(function (p) {
      if (p === "" || p === ".") return;
      if (p === "..") parts.pop();
      else parts.push(p);
    });
    return parts.join("/");
  }

  function inline(text, opt) {
    opt = opt || {};
    // protect inline code first
    var codes = [];
    text = text.replace(/`([^`]+)`/g, function (_, c) {
      codes.push("<code>" + esc(c) + "</code>");
      return "\u0000" + (codes.length - 1) + "\u0000";
    });
    text = esc(text);
    // images
    text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, function (_, alt, src) {
      return '<img alt="' + alt + '" src="' + joinPath(opt.baseDir, src) + '" />';
    });
    // links (rewrite .md links to the viewer so browsing stays in-page)
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, function (_, t, href) {
      var h = href;
      if (/\.md$/i.test(href) && !/^[a-z]+:\/\//i.test(href)) {
        h = "view.html?doc=" + encodeURIComponent(joinPath(opt.baseDir, href));
      } else if (!/^([a-z]+:)?\/\//i.test(href) && !href.startsWith("#")) {
        h = joinPath(opt.baseDir, href);
      }
      return '<a href="' + h + '">' + t + "</a>";
    });
    // bold then italic (asterisks, then boundary-safe underscores)
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1<em>$2</em>");
    text = text.replace(/(^|[\s(>])_([^_\n]+)_(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>");
    // hard line break: two spaces at end of line
    text = text.replace(/ {2}\n/g, "<br/>\n");
    // restore code
    text = text.replace(/\u0000(\d+)\u0000/g, function (_, i) { return codes[+i]; });
    return text;
  }

  function isTableSep(line) {
    return /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(line) && line.indexOf("-") !== -1;
  }
  function splitRow(line) {
    var s = line.trim().replace(/^\|/, "").replace(/\|$/, "");
    return s.split("|").map(function (c) { return c.trim(); });
  }

  function render(md, opt) {
    opt = opt || {};
    md = md.replace(/\r\n?/g, "\n");
    // strip the injected TG-BRAND banner (the live page shows its own header)
    md = md.replace(/<!--\s*TG-BRAND\s*-->[\s\S]*?\n---\n/, "");
    var lines = md.split("\n");
    var out = [], i = 0;

    while (i < lines.length) {
      var line = lines[i];

      // blank
      if (/^\s*$/.test(line)) { i++; continue; }

      // fenced code
      var fence = line.match(/^\s*```(.*)$/);
      if (fence) {
        var buf = []; i++;
        while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { buf.push(lines[i]); i++; }
        i++; // closing fence
        out.push("<pre><code>" + esc(buf.join("\n")) + "</code></pre>");
        continue;
      }

      // heading
      var h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) { var n = h[1].length; out.push("<h" + n + ">" + inline(h[2], opt) + "</h" + n + ">"); i++; continue; }

      // hr
      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { out.push("<hr/>"); i++; continue; }

      // table
      if (line.indexOf("|") !== -1 && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        var head = splitRow(line), rows = []; i += 2;
        while (i < lines.length && lines[i].indexOf("|") !== -1 && !/^\s*$/.test(lines[i])) {
          rows.push(splitRow(lines[i])); i++;
        }
        var t = '<table><thead><tr>' + head.map(function (c) { return "<th>" + inline(c, opt) + "</th>"; }).join("") + "</tr></thead><tbody>";
        rows.forEach(function (r) {
          t += "<tr>" + r.map(function (c) { return "<td>" + inline(c, opt) + "</td>"; }).join("") + "</tr>";
        });
        t += "</tbody></table>";
        out.push(t);
        continue;
      }

      // blockquote
      if (/^\s*>\s?/.test(line)) {
        var q = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) { q.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
        out.push("<blockquote>" + render(q.join("\n"), opt) + "</blockquote>");
        continue;
      }

      // lists
      var lm = line.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);
      if (lm) {
        var ordered = /\d+\./.test(lm[2]);
        var items = [];
        while (i < lines.length) {
          var m = lines[i].match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);
          if (!m) {
            // continuation line (indented) appends to last item
            if (/^\s+\S/.test(lines[i]) && items.length) { items[items.length - 1] += " " + lines[i].trim(); i++; continue; }
            break;
          }
          items.push(m[3]); i++;
        }
        var tag = ordered ? "ol" : "ul";
        out.push("<" + tag + ">" + items.map(function (it) { return "<li>" + inline(it, opt) + "</li>"; }).join("") + "</" + tag + ">");
        continue;
      }

      // paragraph
      var para = [];
      while (i < lines.length && !/^\s*$/.test(lines[i]) &&
             !/^\s*```/.test(lines[i]) && !/^#{1,6}\s/.test(lines[i]) &&
             !/^\s*>\s?/.test(lines[i]) && !/^\s*([-*+]|\d+\.)\s+/.test(lines[i]) &&
             !/^\s*([-*_])(\s*\1){2,}\s*$/.test(lines[i]) &&
             !(lines[i].indexOf("|") !== -1 && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
        para.push(lines[i]); i++;
      }
      out.push("<p>" + inline(para.join("\n"), opt) + "</p>");
    }
    return out.join("\n");
  }

  global.TGMarkdown = { render: render };
  if (typeof module !== "undefined" && module.exports) module.exports = { render: render };
})(typeof window !== "undefined" ? window : this);
