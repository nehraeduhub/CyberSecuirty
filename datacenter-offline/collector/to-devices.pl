#!/usr/bin/perl
# Read what one collection step saved (netdiscovery / netinventory XML, remote
# and VMware inventory JSON) and send it to the manager's device list.
# Prints "<files> <devices sent>" for collect.sh.
#
#   perl to-devices.pl <folder> <source-name>
use strict;
use warnings;
use File::Find;
use JSON::PP;
use LWP::UserAgent;
use Encode qw(decode);

my ($dir, $source) = @ARGV;
my $manager = ($ENV{MANAGER_URL} || 'http://manager:8090') =~ s{/+$}{}r;
my (%dev, $files);

sub is_ip { ($_[0] // '') =~ /^(\d{1,3}\.){3}\d{1,3}$/ && $_[0] !~ /^(127\.|169\.254\.|0\.)/ }

sub merge {   # same IP from two files: keep the first non-empty value of each field
    my ($d) = @_;
    return unless is_ip($d->{ip});
    my $t = $dev{ $d->{ip} } //= { ip => $d->{ip} };
    for my $k (keys %$d) { $t->{$k} = $d->{$k} if defined $d->{$k} && length $d->{$k} && !length($t->{$k} // '') }
    $t->{snmp} = 1 if $d->{snmp};
}

sub unxml { my $v = shift // ''; $v =~ s/&lt;/</g; $v =~ s/&gt;/>/g; $v =~ s/&quot;/"/g; $v =~ s/&apos;/'/g; $v =~ s/&amp;/&/g; $v }

# Direct children <TAG>value</TAG> of a block (nested blocks are skipped)
sub tags {
    my ($block) = @_;
    my %t;
    $block =~ s{<(IPS|PORTS|COMPONENTS|FIRMWARES|MODEMS|SIMCARDS|PAGECOUNTERS|CARTRIDGES|STORAGES|DRIVES)>.*?</\1>}{}gs;
    $t{$1} //= unxml($2) while $block =~ m{<([A-Z_]+)>([^<]*)</\1>}g;
    return \%t;
}

sub xml_file {
    my ($text) = @_;
    my ($query) = $text =~ m{<QUERY>([^<]+)</QUERY>};
    if (($query // '') eq 'NETDISCOVERY') {
        while ($text =~ m{<DEVICE>(.*?)</DEVICE>}gs) {
            my $t = tags($1);
            merge({ ip => $t->{IP}, name => $t->{SNMPHOSTNAME}, manufacturer => $t->{MANUFACTURER}, model => $t->{MODEL},
                    serial => $t->{SERIAL}, mac => $t->{MAC}, type => $t->{TYPE}, description => $t->{DESCRIPTION},
                    firmware => $t->{FIRMWARE}, location => $t->{LOCATION}, snmp => defined $t->{AUTHSNMP} });
        }
    } else {   # SNMPQUERY / netinventory: richer INFO block
        my ($info) = $text =~ m{<INFO>(.*?)</INFO>}s or return;
        my ($ips) = $info =~ m{<IPS>(.*?)</IPS>}s;
        my ($ip) = ($ips // '') =~ m{<IP>([^<]+)</IP>};
        my $t = tags($info);
        merge({ ip => $ip || $t->{IP}, name => $t->{NAME}, manufacturer => $t->{MANUFACTURER}, model => $t->{MODEL},
                serial => $t->{SERIAL}, mac => $t->{MAC}, type => $t->{TYPE}, description => $t->{COMMENTS},
                firmware => $t->{FIRMWARE}, location => $t->{LOCATION}, snmp => 1 });
    }
}

# Computer inventory (SSH/WinRM remote, VMware host) in GLPI Agent JSON format
sub json_file {
    my ($text) = @_;
    my $j = eval { decode_json($text) } or return;
    my $c = $j->{content} || $j;
    my $hw = $c->{hardware} || {};
    my $bios = $c->{bios} || {};
    my ($net) = grep { is_ip($_->{ipaddress}) && ($_->{type} // '') ne 'loopback' && ($_->{description} // '') !~ /^(docker|br-|veth|virbr|lo)/ }
                @{ ref $c->{networks} eq 'ARRAY' ? $c->{networks} : [] };
    return unless $net;
    merge({ ip => $net->{ipaddress}, name => $hw->{name}, manufacturer => $bios->{smanufacturer} || $bios->{mmanufacturer},
            model => $bios->{smodel} || $bios->{mmodel}, serial => $bios->{ssn} || $bios->{msn}, mac => $net->{macaddr},
            type => 'COMPUTER', description => join(' ', grep { $_ } ($c->{operatingsystem} || {})->{full_name}, ($c->{operatingsystem} || {})->{version}) });
}

find({ no_chdir => 1, wanted => sub {
    return unless -f $_;
    open my $fh, '<', $_ or return;
    local $/; my $text = <$fh>;
    close $fh;
    $text = decode('UTF-8', $text);   # characters, so encode_json writes them once
    $files++;
    if ($text =~ /^\s*</) { xml_file($text) } elsif ($text =~ /^\s*\{/) { json_file($text) }
} }, $dir) if -d $dir;

my $sent = 0;
if (%dev) {
    my $ua = LWP::UserAgent->new(timeout => 60);
    my $r = $ua->post("$manager/api/import", 'Content-Type' => 'application/json',
        Content => encode_json({ source => $source || 'scan', devices => [ values %dev ] }));
    if ($r->is_success) { $sent = scalar keys %dev }
    else { print STDERR "manager import failed: ", $r->status_line, "\n" }
}
print +($files || 0), " $sent\n";
