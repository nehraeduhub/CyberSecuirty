#!/usr/bin/perl
# DC Viewer management API: the settings people change in the browser (networks
# to scan, SNMP credentials, scan options, which features are on), device
# up/down status from Prometheus, and "scan now". Served by the portal under
# /api/. Sign-in is the user's GLPI session (the DC Viewer sends its
# Session-Token); changing settings needs a GLPI profile with the Setup >
# General "Update" right (Super-Admin, Admin).
#
# Environment:
#   LISTEN          0.0.0.0:8090
#   GLPI_URL        http://glpi
#   PROMETHEUS_URL  http://prometheus:9090
#   SETTINGS_FILE   /settings/settings.json   (read by the collector and monitor-sync)
#   SCAN_REQUEST    /status/scan-request      (the collector starts a run when it appears)
#   SYNC_REQUEST    /settings/sync-request    (monitor-sync re-reads GLPI when it appears)
#   DISCOVER_SCRIPT /opt/discover-networks.pl
use strict;
use warnings;
use HTTP::Daemon;
use HTTP::Status qw(:constants);
use HTTP::Response;
use LWP::UserAgent;
use JSON::PP;
use URI::Escape qw(uri_escape);
use POSIX qw(strftime);

my $listen   = $ENV{LISTEN} || '0.0.0.0:8090';
my $glpi     = ($ENV{GLPI_URL} || 'http://glpi') =~ s{/+$}{}r;
my $prom     = ($ENV{PROMETHEUS_URL} || 'http://prometheus:9090') =~ s{/+$}{}r;
my $file     = $ENV{SETTINGS_FILE} || '/settings/settings.json';
my $scan_req = $ENV{SCAN_REQUEST} || '/status/scan-request';
my $sync_req = $ENV{SYNC_REQUEST} || '/settings/sync-request';
my $discover = $ENV{DISCOVER_SCRIPT} || '/opt/discover-networks.pl';

my $json = JSON::PP->new->utf8->canonical->pretty;
my $ua   = LWP::UserAgent->new(timeout => 20, agent => 'dc-manager');
my $MASK = '********';
$| = 1;

sub logmsg { printf "%s %s\n", strftime('%F %T', localtime), join('', @_) }

# ------------------------------------------------------------------ settings
# Defaults for a fresh install: only the Devices list and network scanning;
# everything else can be switched on from the Scan & settings page.
sub defaults {
    return {
        networks => [],
        snmp     => [],
        scan     => { interval_minutes => 60, threads => 32, timeout => 2 },
        features => {
            racks => JSON::PP::false, inventory => JSON::PP::false, grafana => JSON::PP::false,
            library => JSON::PP::true, servers => JSON::PP::false, vmware => JSON::PP::false,
            monitor_unidentified => JSON::PP::true,
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

# ------------------------------------------------------------------- auth
my %session_cache;   # token -> [expires, info]

# Who is behind this GLPI session token? undef when not signed in.
sub whoami {
    my ($req) = @_;
    my $token = $req->header('Session-Token') or return;
    my $c = $session_cache{$token};
    return $c->[1] if $c && $c->[0] > time;
    my @h = ('Session-Token' => $token);
    push @h, 'App-Token' => $req->header('App-Token') if $req->header('App-Token');
    my $r = $ua->get("$glpi/apirest.php/getFullSession", @h);
    return unless $r->is_success;
    my $s = eval { decode_json($r->decoded_content)->{session} } or return;
    my $p = $s->{glpiactiveprofile} || {};
    my $info = { name => $s->{glpiname} // '', profile => $p->{name} // '', admin => (($p->{config} // 0) & 2) ? 1 : 0 };
    %session_cache = () if keys %session_cache > 500;
    $session_cache{$token} = [ time + 60, $info ];
    return $info;
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

    # Feature switches decide which tabs show; no secrets, so no sign-in needed
    return reply($c, 200, load_settings()->{features}) if $m eq 'GET' && $path eq '/features';

    my $who = whoami($req) or return reply($c, 401, { error => 'Sign in to GLPI first (session missing or expired).' });
    return reply($c, 200, $who) if $m eq 'GET' && $path eq '/whoami';
    return reply($c, 200, device_status()) if $m eq 'GET' && $path eq '/status';
    if ($m eq 'POST' && $path eq '/sync') {
        touch($sync_req);
        return reply($c, 202, { ok => 1 });
    }
    return reply($c, 200, masked(load_settings())) if $m eq 'GET' && $path eq '/settings';

    # Everything below changes the setup
    return reply($c, 403, { error => "Your GLPI profile ($who->{profile}) may not change settings: use an Admin or Super-Admin account." })
        unless $who->{admin};

    if ($m eq 'PUT' && $path eq '/settings') {
        my $new = body($req) or return reply($c, 400, { error => 'Body must be a JSON object' });
        my $old = load_settings();
        my ($s, $err) = merge_settings($old, $new);
        return reply($c, 400, { error => join("\n", @$err) }) if @$err;
        save_settings($s);
        touch($sync_req);
        logmsg("settings saved by $who->{name}: ", scalar @{ $s->{networks} }, " network(s), ", scalar @{ $s->{snmp} }, " credential(s)");
        return reply($c, 200, masked($s));
    }
    if ($m eq 'POST' && $path eq '/scan') {
        touch($scan_req) or return reply($c, 500, { error => "Cannot write $scan_req" });
        logmsg("scan requested by $who->{name}");
        return reply($c, 202, { ok => 1 });
    }
    if ($m eq 'POST' && $path eq '/find-networks') {
        my $b = body($req) || {};
        return reply($c, 400, { error => 'Give the IP address of a router, L3 switch or firewall' }) unless is_ipv4($b->{router});
        return reply($c, 200, find_networks($b->{router}, load_settings()));
    }
    return reply($c, 404, { error => "No such API: $m $path" });
}

my ($host, $port) = split /:/, $listen;
my $d = HTTP::Daemon->new(LocalAddr => $host, LocalPort => $port, ReuseAddr => 1, Timeout => 30)
    or die "Cannot listen on $listen: $!\n";
save_settings(load_settings()) unless -e $file;
logmsg("DC manager API on $listen, settings in $file");
while (1) {
    my $c = $d->accept or next;
    $c->timeout(30);
    while (my $req = $c->get_request) {
        eval { handle($c, $req); 1 } or do { logmsg("error: $@"); reply($c, 500, { error => 'Internal error, see: docker compose logs manager' }) };
        last;   # one request per connection keeps this single-threaded server responsive
    }
    $c->close;
}
