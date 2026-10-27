#!/usr/bin/perl
# Ask routers/L3 switches over SNMP which IPv4 networks exist: their own
# interface subnets (IP-MIB ipAddrTable) and their routing table (ipRouteTable,
# ipCidrRouteTable). Prints one "network/prefix  router  source" line per subnet.
# Runs inside the collector container (Net::SNMP), see discover-networks.sh.
#
#   perl discover-networks.pl <credential-line> <router-ip>...
#   credential-line: as in SNMP_CREDENTIALS, several separated by ';'
use strict;
use warnings;
use Net::SNMP;

my ($credlist, @routers) = @ARGV;
die "usage: $0 <credentials> <router-ip>...\n" unless $credlist && @routers;

my @creds = map {
    my %c = map { my ($k, $v) = split /:/, $_, 2; (lc $k => $v // '') } split /,/, $_;
    \%c
} grep { /version:/ } split /;/, $credlist;
die "No usable SNMP credentials\n" unless @creds;

sub session {
    my ($ip) = @_;
    for my $c (@creds) {
        my %o = (-hostname => $ip, -timeout => 3, -retries => 1, -maxmsgsize => 65535);
        if (($c->{version} // '') eq '3') {
            %o = (%o, -version => 'snmpv3', -username => $c->{username});
            if ($c->{authpassword}) { $o{-authprotocol} = lc($c->{authprotocol} || 'md5'); $o{-authpassword} = $c->{authpassword} }
            if ($c->{privpassword}) { $o{-privprotocol} = lc($c->{privprotocol} || 'des'); $o{-privpassword} = $c->{privpassword} }
        } else {
            %o = (%o, -version => ($c->{version} eq '1' ? 'snmpv1' : 'snmpv2c'), -community => $c->{community} || 'public');
        }
        my ($s, $err) = Net::SNMP->session(%o);
        unless ($s) { warn "  $ip: $err\n" if $err && $err !~ /No response|discovery/i; next }
        my $r = $s->get_request(-varbindlist => ['1.3.6.1.2.1.1.5.0']);
        return ($s, $r->{'1.3.6.1.2.1.1.5.0'}) if $r;
        $s->close;
    }
    return;
}

sub walk {
    my ($s, $oid) = @_;
    my $r = $s->get_table(-baseoid => $oid);
    return $r || {};
}

sub prefix_len { my $m = unpack 'N', pack 'C4', split /\./, shift; my $n = 0; $n++ while $m & (1 << (31 - $n)) && $n < 32; $n }
sub net_of { my ($ip, $mask) = @_; join '.', unpack 'C4', pack('C4', split /\./, $ip) & pack('C4', split /\./, $mask) }

my %seen;
for my $router (@routers) {
    my ($s, $name) = session($router);
    unless ($s) { warn "  $router: no SNMP answer with the given credentials\n"; next }
    warn "  $router ($name): reading interfaces and routes\n";
    my @found;

    # Own interface addresses: ipAdEntNetMask indexed by address
    my $masks = walk($s, '1.3.6.1.2.1.4.20.1.3');
    for my $oid (keys %$masks) {
        my ($ip) = $oid =~ /^1\.3\.6\.1\.2\.1\.4\.20\.1\.3\.(\d+\.\d+\.\d+\.\d+)$/ or next;
        push @found, [ net_of($ip, $masks->{$oid}), prefix_len($masks->{$oid}), 'interface' ];
    }
    # Classic route table: ipRouteMask indexed by destination
    my $rt = walk($s, '1.3.6.1.2.1.4.21.1.11');
    for my $oid (keys %$rt) {
        my ($dst) = $oid =~ /^1\.3\.6\.1\.2\.1\.4\.21\.1\.11\.(\d+\.\d+\.\d+\.\d+)$/ or next;
        push @found, [ $dst, prefix_len($rt->{$oid}), 'route' ];
    }
    # ipCidrRouteTable: index = dest.mask.tos.nexthop
    my $cidr = walk($s, '1.3.6.1.2.1.4.24.4.1.1');
    for my $oid (keys %$cidr) {
        my ($dst, $mask) = $oid =~ /^1\.3\.6\.1\.2\.1\.4\.24\.4\.1\.1\.(\d+\.\d+\.\d+\.\d+)\.(\d+\.\d+\.\d+\.\d+)\./ or next;
        push @found, [ $dst, prefix_len($mask), 'route' ];
    }
    $s->close;

    for my $f (@found) {
        my ($net, $len, $src) = @$f;
        next if $len == 0 || $len == 32;                       # default route, host routes
        next if $net =~ /^(127|0|169\.254|22[4-9]|2[3-5]\d)\./; # loopback, link-local, multicast
        my $key = "$net/$len";
        next if $seen{$key}++;
        print "$key\t$router\t$src\n";
    }
}
