#!/usr/bin/perl
# Keep Prometheus targets in sync with the DC NOC device list (devices.json,
# kept by the manager), every SYNC_MINUTES or right after a change:
#  - ping: every device with an IPv4 address (TARGETS_FILE), labelled with its
#    name and category ("type" in the Grafana dashboards)
#  - SNMP: devices that answered SNMP in a scan, and network-type categories.
#    For each, the first SNMP credential that answers is used, and the vendor
#    is read from sysObjectID to add vendor health metrics.
#
# Environment:
#   DEVICES_FILE       /settings/devices.json
#   PUBLIC_URL         https://10.0.0.5:8443   (links from Grafana to the device page)
#   TARGETS_FILE       /targets/glpi.json      (file name kept for existing installs)
#   SYNC_MINUTES       5
#   COLLECTOR_CONF     /etc/collector/collector.conf   (SNMP_CREDENTIALS are read from it)
#   SNMP_TARGETS_FILE  /targets/snmp.json
#   SNMP_AUTH_FILE     /snmp/auth.yml                  (snmp_exporter auth config)
#   SNMP_EXPORTER_URL  http://snmp-exporter:9116       (reloaded when auth changes)
#   SETTINGS_FILE      /settings/settings.json         (SNMP credentials from the DC Viewer)
#   SYNC_REQUEST       /settings/sync-request          (sync right away when this file appears)
use strict;
use warnings;
use LWP::UserAgent;
use JSON::PP;
use Net::SNMP;

my $devices = $ENV{DEVICES_FILE} || '/settings/devices.json';
my $public  = ($ENV{PUBLIC_URL} || $ENV{GLPI_PUBLIC_URL} || '') =~ s{/+$}{}r;
my $out     = $ENV{TARGETS_FILE} || '/targets/glpi.json';
my $every   = ($ENV{SYNC_MINUTES} || 5) * 60;
my $conf      = $ENV{COLLECTOR_CONF} || '/etc/collector/collector.conf';
my $snmp_out  = $ENV{SNMP_TARGETS_FILE} || '/targets/snmp.json';
my $auth_out  = $ENV{SNMP_AUTH_FILE} || '/snmp/auth.yml';
my $settings  = $ENV{SETTINGS_FILE} || '/settings/settings.json';
my $sync_req  = $ENV{SYNC_REQUEST} || '/settings/sync-request';
my $exporter  = ($ENV{SNMP_EXPORTER_URL} || 'http://snmp-exporter:9116') =~ s{/+$}{}r;

# Categories polled over SNMP even if the scan did not see SNMP answer
my %SNMP_CATEGORIES = map { $_ => 1 } ('Firewall', 'Load balancer', 'Router', 'Switch', 'Wireless', 'Storage', 'Management', 'Power');

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

my $ua   = LWP::UserAgent->new(timeout => 60, agent => 'dc-monitor-sync');
my $json = JSON::PP->new->utf8->canonical->pretty;
$| = 1;

sub logmsg { printf "%s %s\n", scalar localtime, join('', @_) }

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

# Settings made in the DC Viewer, {} when there are none
sub gui_settings {
    open my $fh, '<', $settings or return {};
    local $/; my $raw = <$fh>; close $fh;
    return eval { decode_json($raw) } || {};
}

# SNMP credentials: the DC Viewer's first, then SNMP_CREDENTIALS from collector.conf
sub snmp_credentials {
    my @gui = map { my %c = %$_; delete @c{qw(id name enabled)}; \%c }
              grep { $_->{enabled} && $_->{version} } @{ gui_settings()->{snmp} || [] };
    return (@gui, conf_credentials());
}

# SNMP_CREDENTIALS from collector.conf: one "version:2c,community:x" style line each
sub conf_credentials {
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
        my ($s, $err) = Net::SNMP->session(%opt);
        unless ($s) { warn "SNMP credential ".($i + 1).": $err\n" if $err && $err !~ /No response|discovery/i; next }
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
        next unless ($t->{labels}{snmp} eq 'yes' || $SNMP_CATEGORIES{ $t->{labels}{category} }) && @creds;
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
    my $db = { devices => [] };   # no list yet (fresh install): nothing to monitor
    if (open my $fh, '<', $devices) {
        local $/; my $raw = <$fh>; close $fh;
        $db = decode_json($raw);
    }
    my @targets;
    for my $d (@{ $db->{devices} || [] }) {
        next unless ($d->{ip} // '') =~ /^\d+\.\d+\.\d+\.\d+$/;
        my $cat = $d->{category} || 'Unknown';
        push @targets, {
            targets => [ $d->{ip} ],
            labels  => {
                name     => $d->{name} || $d->{ip},
                type     => $cat,          # Grafana dashboards group and filter by "type"
                category => $cat,
                rack     => $d->{location} // '',
                glpi_id  => "$d->{id}",    # label names kept for the existing dashboards
                status   => '',
                glpi_url => $public ? "$public/viewer/devices.html?q=$d->{ip}" : '',
                snmp     => $d->{snmp} ? 'yes' : 'no',
            },
        };
    }
    @targets = sort { $a->{labels}{name} cmp $b->{labels}{name} } @targets;
    write_file($out, $json->encode(\@targets));
    my $snmp = snmp_targets(\@targets);
    return (scalar @targets, $snmp);
}

my $once = grep { $_ eq '--once' } @ARGV;
while (1) {
    my ($n, $snmp) = eval { sync_once() };
    if (defined $n) { logmsg("synced $n ping target(s) and $snmp SNMP target(s) from the device list") }
    else            { logmsg("sync failed: $@") }
    last if $once;
    # Retry soon after a failure (e.g. no device list yet), else wait the interval
    # A change in the DC Viewer (rename, new device, settings) asks for a sync now
    my $end = time + (defined $n ? $every : 30);
    while (time < $end) {
        if (-e $sync_req) { unlink $sync_req; last }
        sleep 3;
    }
}
