#!/usr/bin/perl
# Turn the settings made in the DC Viewer (settings.json, written by the
# manager API) into shell variables for collect.sh. Networks and SNMP
# credentials from the GUI are added to any in collector.conf; the GUI's
# scan options and feature switches win.
#
#   eval "$(perl settings-env.pl /settings/settings.json)"
use strict;
use warnings;
use JSON::PP;

my $file = shift || '/settings/settings.json';
open my $fh, '<', $file or exit 0;          # no GUI settings: collector.conf only
local $/; my $s = eval { decode_json(<$fh>) } or exit 0;
close $fh;

sub shq { my $v = shift // ''; $v =~ s/'/'\\''/g; "'$v'" }
sub ip2n { unpack 'N', pack 'C4', split /\./, shift }
sub n2ip { join '.', unpack 'C4', pack 'N', shift }

# 10.1.2.0/24 -> 10.1.2.1-10.1.2.254 (the form glpi-netdiscovery takes)
sub range_of {
    my $n = shift;
    if ($n =~ m{^([\d.]+)/(\d+)$}) {
        my $size = 2 ** (32 - $2);
        my $base = ip2n($1) & ~($size - 1) & 0xFFFFFFFF;
        return $2 >= 31 ? n2ip($base) . '-' . n2ip($base + $size - 1) : n2ip($base + 1) . '-' . n2ip($base + $size - 2);
    }
    return $n =~ /-/ ? $n : "$n-$n";
}

my @ranges = map { range_of($_->{network}) . "  # $_->{network}" } grep { $_->{enabled} && $_->{network} } @{ $s->{networks} || [] };
my @creds;
for my $c (grep { $_->{enabled} } @{ $s->{snmp} || [] }) {
    my @p = ("version:$c->{version}");
    for my $k (qw(community username authprotocol authpassword privprotocol privpassword)) {
        push @p, "$k:$c->{$k}" if defined $c->{$k} && length $c->{$k};
    }
    push @creds, join ',', @p;
}

print 'SNMP_RANGES="${SNMP_RANGES:-}"', "\n";
print 'SNMP_RANGES+=', shq("\n" . join("\n", @ranges)), "\n" if @ranges;
print 'SNMP_CREDENTIALS="${SNMP_CREDENTIALS:-}"', "\n";
# GUI credentials first: they are the ones people maintain
print 'SNMP_CREDENTIALS=', shq(join("\n", @creds) . "\n"), '"$SNMP_CREDENTIALS"', "\n" if @creds;
my $sc = $s->{scan} || {};
print "INTERVAL_MINUTES=", shq($sc->{interval_minutes}), "\n" if $sc->{interval_minutes};
print "THREADS=", shq($sc->{threads}), "\n" if $sc->{threads};
print "SNMP_TIMEOUT=", shq($sc->{timeout}), "\n" if $sc->{timeout};
my $f = $s->{features} || {};
print "REMOTES=''\n" if exists $f->{servers} && !$f->{servers};
print "ESX_HOSTS=''\n" if exists $f->{vmware} && !$f->{vmware};
