#!/usr/bin/perl
# Keep Prometheus targets in sync with GLPI, every SYNC_MINUTES:
#  - ping: every device in GLPI with an IPv4 address (TARGETS_FILE)
#  - SNMP: every network device (switches, routers, firewalls, load balancers,
#    iLO/iDRAC, SNMP PDUs). For each, the first SNMP credential from the
#    collector settings that answers is used, and the vendor is read from
#    sysObjectID to add vendor health metrics (SNMP_TARGETS_FILE, SNMP_AUTH_FILE).
#
# Environment:
#   GLPI_URL           http://glpi            GLPI base URL (inside the stack)
#   GLPI_PUBLIC_URL    http://10.0.0.5/       GLPI as users reach it (for links in Grafana)
#   GLPI_USER          dc-monitor             read-only GLPI account
#   GLPI_PASSWORD                              its password
#   TARGETS_FILE       /targets/glpi.json
#   SYNC_MINUTES       5
#   MONITOR_TYPES      Computer,NetworkEquipment,PDU,Printer,Phone,Peripheral,Enclosure
#   EXCLUDE_STATES     comma list of GLPI statuses to skip, e.g. "Retired,In stock"
#   COLLECTOR_CONF     /etc/collector/collector.conf   (SNMP_CREDENTIALS are read from it)
#   SNMP_TARGETS_FILE  /targets/snmp.json
#   SNMP_AUTH_FILE     /snmp/auth.yml                  (snmp_exporter auth config)
#   SNMP_EXPORTER_URL  http://snmp-exporter:9116       (reloaded when auth changes)
use strict;
use warnings;
use LWP::UserAgent;
use JSON::PP;
use MIME::Base64;
use Net::SNMP;

my $base    = ($ENV{GLPI_URL} || 'http://glpi') =~ s{/+$}{}r;
my $public  = ($ENV{GLPI_PUBLIC_URL} || '') =~ s{/+$}{}r;
my $user    = $ENV{GLPI_USER} || 'dc-monitor';
my $pass    = $ENV{GLPI_PASSWORD} // '';
my $out     = $ENV{TARGETS_FILE} || '/targets/glpi.json';
my $every   = ($ENV{SYNC_MINUTES} || 5) * 60;
my @types   = split /\s*,\s*/, ($ENV{MONITOR_TYPES} || 'Computer,NetworkEquipment,PDU,Printer,Phone,Peripheral,Enclosure');
my %exclude = map { lc($_) => 1 } grep { length } split /\s*,\s*/, ($ENV{EXCLUDE_STATES} || '');
my $conf      = $ENV{COLLECTOR_CONF} || '/etc/collector/collector.conf';
my $snmp_out  = $ENV{SNMP_TARGETS_FILE} || '/targets/snmp.json';
my $auth_out  = $ENV{SNMP_AUTH_FILE} || '/snmp/auth.yml';
my $exporter  = ($ENV{SNMP_EXPORTER_URL} || 'http://snmp-exporter:9116') =~ s{/+$}{}r;

# GLPI types that answer SNMP
my %SNMP_TYPES = map { $_ => 1 } qw(NetworkEquipment PDU Printer);

# sysObjectID prefix -> vendor and extra snmp_exporter module for health metrics
my @VENDORS = (
    [ '1.3.6.1.4.1.2604.',        'Sophos',   'sophos_xg' ],
    [ '1.3.6.1.4.1.9.',           'Cisco',    'cisco_device' ],
    [ '1.3.6.1.4.1.232.',         'HPE',      'hpe' ],          # iLO
    [ '1.3.6.1.4.1.674.10892.',   'Dell',     'dell' ],         # iDRAC
    [ '1.3.6.1.4.1.674.11000.',   'Dell',     'dell_network' ], # OS10 switches
    [ '1.3.6.1.4.1.6027.',        'Dell',     'dell_network' ],
    [ '1.3.6.1.4.1.674.',         'Dell',     '' ],
    [ '1.3.6.1.4.1.1872.',        'Radware',  '' ],             # Alteon
    [ '1.3.6.1.4.1.89.',          'Radware',  '' ],
    [ '1.3.6.1.4.1.47196.',       'HPE Aruba', '' ],
    [ '1.3.6.1.4.1.11.',          'HP',       '' ],
    [ '1.3.6.1.4.1.25506.',       'HPE',      '' ],             # H3C / Comware
);

my %snmp_cache;   # ip -> { auth => credN, oid => sysObjectID }

my %LABEL = (
    Computer => 'Server', NetworkEquipment => 'Network', PDU => 'Power',
    Printer => 'Printer', Phone => 'Phone', Peripheral => 'Peripheral', Enclosure => 'Enclosure',
);

my $ua   = LWP::UserAgent->new(timeout => 60, agent => 'dc-monitor-sync');
my $json = JSON::PP->new->utf8->canonical->pretty;
$| = 1;

sub logmsg { printf "%s %s\n", scalar localtime, join('', @_) }

sub api {
    my ($token, $path) = @_;
    my $res = $ua->get("$base/apirest.php/$path", 'Session-Token' => $token, 'Content-Type' => 'application/json');
    return ($res, $res->is_success ? decode_json($res->decoded_content || 'null') : undef);
}

# All non-deleted objects of an itemtype, paging through the API
sub fetch_all {
    my ($token, $itemtype, $extra) = @_;
    my (@all, $start);
    $start = 0;
    while (1) {
        my $end = $start + 999;
        my ($res, $data) = api($token, "$itemtype?is_deleted=0&range=$start-$end" . ($extra ? "&$extra" : ''));
        if (!$res->is_success) {
            last if $res->decoded_content =~ /ERROR_RANGE_EXCEED_TOTAL/;
            # Missing right on one type must not stop the sync
            if ($res->code == 401 && $res->decoded_content =~ /ERROR_RIGHT_MISSING/) { last }
            die "GET $itemtype: " . $res->status_line . ' ' . $res->decoded_content . "\n";
        }
        push @all, @{ $data || [] };
        my ($total) = ($res->header('Content-Range') // '') =~ m{/(\d+)$};
        last if !$total || $end + 1 >= $total;
        $start += 1000;
    }
    return \@all;
}

# Write a file atomically; returns 1 when the content changed
sub write_file {
    my ($path, $content) = @_;
    if (open my $old, '<', $path) { local $/; my $cur = <$old>; close $old; return 0 if defined $cur && $cur eq $content }
    my $tmp = "$path.tmp";
    open my $fh, '>', $tmp or die "write $tmp: $!\n";
    print $fh $content;
    close $fh;
    rename $tmp, $path or die "rename $tmp: $!\n";
    return 1;
}

# SNMP_CREDENTIALS from collector.conf: one "version:2c,community:x" style line each
sub snmp_credentials {
    open my $fh, '<', $conf or return ();
    local $/; my $text = <$fh>; close $fh;
    my ($block) = $text =~ /^SNMP_CREDENTIALS="(.*?)"/ms or return ();
    my @creds;
    for my $line (split /\n/, $block) {
        $line =~ s/\s+#.*$//;
        $line =~ s/^\s+|\s+$//g;
        next if $line eq '' || $line =~ /^#/;
        my %c = map { my ($k, $v) = split /:/, $_, 2; (lc $k => $v // '') } split /,/, $line;
        push @creds, \%c if $c{version};
    }
    return @creds;
}

sub yaml_str { my $v = shift // ''; $v =~ s/'/''/g; "'$v'" }

# snmp_exporter "auths" section, one entry per credential (cred1, cred2...)
sub auth_yaml {
    my @creds = @_;
    my $y = "# Generated by monitor-sync from collector/collector.conf - do not edit\nauths:\n";
    # snmp_exporter refuses an empty auths list: keep a placeholder until
    # SNMP_CREDENTIALS are configured (no target uses it)
    $y .= "  unconfigured:\n    version: 2\n    community: 'not-configured'\n" unless @creds;
    my $i = 0;
    for my $c (@creds) {
        $i++;
        $y .= "  cred$i:\n";
        if ($c->{version} eq '3') {
            my $level = $c->{privpassword} ? 'authPriv' : $c->{authpassword} ? 'authNoPriv' : 'noAuthNoPriv';
            $y .= "    version: 3\n    username: " . yaml_str($c->{username}) . "\n    security_level: $level\n";
            if ($c->{authpassword}) {
                $y .= "    password: " . yaml_str($c->{authpassword}) . "\n";
                $y .= "    auth_protocol: " . uc($c->{authprotocol} || 'md5') . "\n";
            }
            if ($c->{privpassword}) {
                $y .= "    priv_password: " . yaml_str($c->{privpassword}) . "\n";
                $y .= "    priv_protocol: " . uc($c->{privprotocol} || 'des') . "\n";
            }
        } else {
            $y .= "    version: " . ($c->{version} eq '1' ? 1 : 2) . "\n";
            $y .= "    community: " . yaml_str($c->{community} || 'public') . "\n";
        }
    }
    return $y;
}

# Try credentials in order (last working one first); return (index, sysObjectID)
sub snmp_probe {
    my ($ip, $creds) = @_;
    my @order = (0 .. $#$creds);
    if (my $known = $snmp_cache{$ip}) {
        my ($n) = $known->{auth} =~ /(\d+)$/;
        @order = ($n - 1, grep { $_ != $n - 1 } @order) if $n && $n <= @$creds;
    }
    for my $i (@order) {
        my $c = $creds->[$i];
        my %opt = (-hostname => $ip, -timeout => 2, -retries => 1);
        if ($c->{version} eq '3') {
            %opt = (%opt, -version => 'snmpv3', -username => $c->{username});
            if ($c->{authpassword}) { $opt{-authprotocol} = lc($c->{authprotocol} || 'md5'); $opt{-authpassword} = $c->{authpassword} }
            if ($c->{privpassword}) { $opt{-privprotocol} = lc($c->{privprotocol} || 'des'); $opt{-privpassword} = $c->{privpassword} }
        } else {
            %opt = (%opt, -version => ($c->{version} eq '1' ? 'snmpv1' : 'snmpv2c'), -community => $c->{community} || 'public');
        }
        my ($s) = Net::SNMP->session(%opt) or next;
        my $r = $s->get_request(-varbindlist => ['1.3.6.1.2.1.1.2.0']);
        $s->close;
        next unless $r && defined $r->{'1.3.6.1.2.1.1.2.0'};
        my $oid = $r->{'1.3.6.1.2.1.1.2.0'} =~ s/^\.//r;
        return ($i, $oid);
    }
    return;
}

sub snmp_targets {
    my ($ping) = @_;
    my @creds = snmp_credentials();
    if (write_file($auth_out, auth_yaml(@creds))) {
        my $r = $ua->post("$exporter/-/reload");
        logmsg('SNMP credentials updated' . ($r->is_success ? '' : ' (exporter reload pending: ' . $r->status_line . ')'));
    }
    my @out;
    for my $t (@$ping) {
        next unless $SNMP_TYPES{ $t->{labels}{itemtype} } && @creds;
        my $ip = $t->{targets}[0];
        my ($i, $oid) = snmp_probe($ip, \@creds);
        next unless defined $i;
        $snmp_cache{$ip} = { auth => 'cred' . ($i + 1), oid => $oid };
        my ($vendor, $module) = ('Other', '');
        for my $v (@VENDORS) {
            if (index("$oid.", $v->[0]) == 0) { ($vendor, $module) = @$v[1, 2]; last }
        }
        push @out, {
            targets => [$ip],
            labels  => {
                %{ $t->{labels} },
                auth   => 'cred' . ($i + 1),
                module => join(',', 'if_mib', 'system', $module || ()),
                vendor => $vendor,
            },
        };
    }
    write_file($snmp_out, $json->encode(\@out));
    return scalar @out;
}

sub sync_once {
    my $res = $ua->get("$base/apirest.php/initSession",
        Authorization => 'Basic ' . encode_base64("$user:$pass", ''));
    die "GLPI login failed for '$user': " . $res->status_line . ' ' . $res->decoded_content . "\n"
        unless $res->is_success;
    my $token = decode_json($res->decoded_content)->{session_token};

    my (%ip, %rack, @targets);
    eval {
        for my $a (@{ fetch_all($token, 'IPAddress') }) {
            next unless ($a->{version} // 0) == 4 && $a->{name} && $a->{mainitemtype};
            next if $a->{name} =~ /^(127\.|169\.254\.|0\.)/;
            my $k = "$a->{mainitemtype}:$a->{mainitems_id}";
            $ip{$k} = $a->{name} unless $ip{$k};
        }
        my %racks = map { $_->{id} => $_ } @{ fetch_all($token, 'Rack') };
        for my $m (@{ fetch_all($token, 'Item_Rack') }) {
            my $r = $racks{ $m->{racks_id} } or next;
            $rack{"$m->{itemtype}:$m->{items_id}"} = $r->{name};
        }
        for my $t (@types) {
            for my $it (@{ fetch_all($token, $t, 'expand_dropdowns=true') }) {
                next if $it->{is_template};
                my $k = "$t:$it->{id}";
                my $addr = $ip{$k} or next;
                my $state = $it->{states_id};
                $state = '' if !defined $state || $state eq '0' || $state eq '&nbsp;';
                next if length $state && $exclude{ lc $state };
                push @targets, {
                    targets => [$addr],
                    labels  => {
                        name     => $it->{name} || $addr,
                        itemtype => $t,
                        type     => $LABEL{$t} || $t,
                        rack     => $rack{$k} // '',
                        glpi_id  => "$it->{id}",
                        status   => $state,
                        glpi_url => $public ? "$public/front/" . lc($t) . ".form.php?id=$it->{id}" : '',
                    },
                };
            }
        }
        1;
    } or do { my $e = $@; api($token, 'killSession'); die $e };
    api($token, 'killSession');

    # One target per address: GLPI can hold duplicates of the same device; keep
    # the record placed in a rack, else the first by name
    my %by_ip;
    for my $t (sort { ($b->{labels}{rack} ne '') <=> ($a->{labels}{rack} ne '') || $a->{labels}{name} cmp $b->{labels}{name} } @targets) {
        $by_ip{ $t->{targets}[0] } //= $t;
    }
    @targets = sort { $a->{labels}{name} cmp $b->{labels}{name} } values %by_ip;
    write_file($out, $json->encode(\@targets));
    my $snmp = snmp_targets(\@targets);
    return (scalar @targets, $snmp);
}

my $once = grep { $_ eq '--once' } @ARGV;
while (1) {
    my ($n, $snmp) = eval { sync_once() };
    if (defined $n) { logmsg("synced $n ping target(s) and $snmp SNMP target(s) from GLPI") }
    else            { logmsg("sync failed: $@") }
    last if $once;
    # Retry soon after a failure (e.g. GLPI still starting), else wait the interval
    sleep(defined $n ? $every : 30);
}
