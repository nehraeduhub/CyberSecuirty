#!/usr/bin/perl
# One-time copy of the device list out of GLPI into the DC NOC device list
# (devices.json), used by install-offline.sh when it removes GLPI from an
# older install. Keeps names, make, model, serial, MAC and the categories set
# in the DC Viewer. Does nothing if devices.json already exists.
#
# Runs in the collector image on the stack's network:
#   GLPI_URL=http://glpi GLPI_USER=dc-monitor GLPI_PASSWORD=… perl migrate-from-glpi.pl
use strict;
use warnings;
use LWP::UserAgent;
use JSON::PP;
use MIME::Base64;

my $glpi     = ($ENV{GLPI_URL} || 'http://glpi') =~ s{/+$}{}r;
my $user     = $ENV{GLPI_USER} || 'dc-monitor';
my $pass     = $ENV{GLPI_PASSWORD} // '';
my $dev_file = $ENV{DEVICES_FILE} || '/settings/devices.json';
my $settings = $ENV{SETTINGS_FILE} || '/settings/settings.json';
my $ua = LWP::UserAgent->new(timeout => 60);
my $json = JSON::PP->new->utf8->canonical->pretty;

if (-s $dev_file) { print "Device list already exists, nothing to copy from GLPI.\n"; exit 0 }

my $r = $ua->get("$glpi/apirest.php/initSession", Authorization => 'Basic ' . encode_base64("$user:$pass", ''));
die "GLPI login of '$user' failed: " . $r->status_line . "\n" unless $r->is_success;
my $token = decode_json($r->decoded_content)->{session_token};

sub all {
    my ($type, $extra) = @_;
    my ($start, @out) = (0);
    while (1) {
        my $res = $ua->get("$glpi/apirest.php/$type?is_deleted=0&range=$start-" . ($start + 999) . ($extra ? "&$extra" : ''), 'Session-Token' => $token);
        last unless $res->is_success;
        push @out, @{ decode_json($res->decoded_content || '[]') };
        my ($total) = ($res->header('Content-Range') // '') =~ m{/(\d+)$};
        last if !$total || $start + 1000 >= $total;
        $start += 1000;
    }
    return \@out;
}
sub drop { my $v = shift; return '' if !defined $v || $v eq '0' || $v eq '&nbsp;'; return "$v" }
sub ipnum { my @p = split /\./, shift; (($p[0] * 256 + $p[1]) * 256 + $p[2]) * 256 + $p[3] }

my (%ip, %mac);
for my $a (@{ all('IPAddress') }) {
    next unless ($a->{version} // 0) == 4 && $a->{name} && $a->{mainitemtype} && $a->{name} !~ /^(127\.|169\.254\.|0\.)/;
    my $k = "$a->{mainitemtype}:$a->{mainitems_id}";
    $ip{$k} = $a->{name} if !$ip{$k} || ipnum($a->{name}) < ipnum($ip{$k});
}
for my $p (@{ all('NetworkPort') }) {
    $mac{"$p->{itemtype}:$p->{items_id}"} //= $p->{mac} if $p->{mac} && $p->{mac} !~ /^(00:){5}00$/;
}
my %TYPE = (NetworkEquipment => 'NETWORKING', Computer => 'COMPUTER', Printer => 'PRINTER', Phone => 'PHONE', PDU => 'NETWORKING');
my $over = do { open my $fh, '<', $settings; local $/; my $s = $fh ? eval { decode_json(<$fh>) } : undef; ($s || {})->{categories} || {} };

my (%by, $id);
for my $type (qw(NetworkEquipment Computer PDU Printer Phone Peripheral Unmanaged)) {
    for my $it (sort { $a->{id} <=> $b->{id} } @{ all($type, 'expand_dropdowns=true') }) {
        next if $it->{is_template} || ($type eq 'Unmanaged' && $it->{hub});
        my $k = "$type:$it->{id}";
        my $addr = $ip{$k} || ($type eq 'Unmanaged' && ($it->{ip} // '') =~ /^\d+\.\d+\.\d+\.\d+$/ ? $it->{ip} : '') or next;
        next if $by{$addr} && $type eq 'Unmanaged';   # an identified device wins
        my ($mk) = grep { /models_id$/ } keys %$it;
        my $name = $it->{name} || $addr;
        my %d = (id => ++$id, ip => $addr, name => $name, brand => drop($it->{manufacturers_id}),
                 model => drop($mk ? $it->{$mk} : ''), serial => $it->{serial} // '', mac => $mac{$k} // '',
                 type => $TYPE{$type} // '', source => 'glpi', locked => {},
                 last_seen => ($it->{last_inventory_update} // '') =~ s/ /T/r);
        $d{snmp} = JSON::PP::true if $type ne 'Unmanaged' && $type ne 'Computer';
        $d{locked}{name} = JSON::PP::true if $name ne $addr;
        if (my $c = $over->{$addr}) { $d{category} = $c; $d{locked}{category} = JSON::PP::true }
        $by{$addr} = \%d;
    }
}
$ua->get("$glpi/apirest.php/killSession", 'Session-Token' => $token);

my @list = sort { ipnum($a->{ip}) <=> ipnum($b->{ip}) } values %by;
open my $fh, '>', "$dev_file.tmp" or die "write $dev_file.tmp: $!\n";
print $fh $json->encode({ devices => \@list, next_id => ($id // 0) + 1 });
close $fh;
rename "$dev_file.tmp", $dev_file or die "rename: $!\n";
print "Copied ", scalar @list, " device(s) from GLPI into the DC NOC device list.\n";
