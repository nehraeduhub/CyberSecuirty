package SnmpFacts;
# Read a device's identity straight over SNMP: name, description, make (from
# the sysObjectID enterprise number), and model / serial number / make from
# ENTITY-MIB (RFC 6933), which most switches, routers, firewalls, load
# balancers and management cards implement. Used by the collector after a
# scan (for devices the scanner could not identify) and by the manager's
# "Read from device" button. Shared by both containers (/opt/lib).
use strict;
use warnings;
use Net::SNMP;

# IANA enterprise numbers -> make
my %ENTERPRISE = (
    9 => 'Cisco', 11 => 'HP', 43 => '3Com', 171 => 'D-Link', 232 => 'Hewlett Packard Enterprise', 311 => 'Microsoft',
    318 => 'APC', 534 => 'Eaton', 674 => 'Dell', 1588 => 'Brocade', 1872 => 'Radware', 1916 => 'Extreme Networks',
    1991 => 'Brocade', 2011 => 'Huawei', 2021 => 'Net-SNMP', 2272 => 'Nortel', 2604 => 'Sophos', 2620 => 'Check Point',
    2636 => 'Juniper', 3375 => 'F5', 3076 => 'Cisco', 4526 => 'Netgear', 5624 => 'Enterasys', 5951 => 'Citrix',
    6027 => 'Dell', 6486 => 'Alcatel-Lucent', 6876 => 'VMware', 8072 => 'Net-SNMP', 9148 => 'Cisco', 10002 => 'Ubiquiti',
    11863 => 'TP-Link', 12356 => 'Fortinet', 12325 => 'pfSense', 14179 => 'Cisco', 14823 => 'Aruba', 14988 => 'MikroTik',
    17163 => 'Riverbed', 21296 => 'Infortrend', 22610 => 'A10 Networks', 25053 => 'Ruckus', 25461 => 'Palo Alto Networks',
    25506 => 'H3C', 26866 => 'Gigamon', 30065 => 'Arista', 41112 => 'Ubiquiti', 47196 => 'HPE Aruba', 476 => 'Vertiv',
    13742 => 'Raritan', 789 => 'NetApp', 1139 => 'Dell EMC', 12740 => 'Dell EMC', 4413 => 'Broadcom', 8741 => 'SonicWall',
    3224 => 'Juniper', 6889 => 'Avaya', 89 => 'Radware', 7244 => 'Lenovo', 19046 => 'Lenovo', 2 => 'IBM', 20301 => 'Lenovo',
    10418 => 'Avocent', 12148 => 'Eltek', 3417 => 'Blue Coat', 2352 => 'Ericsson', 637 => 'Nokia',
);

my %O = (
    sysDescr => '1.3.6.1.2.1.1.1.0', sysObjectID => '1.3.6.1.2.1.1.2.0', sysName => '1.3.6.1.2.1.1.5.0',
    sysLocation => '1.3.6.1.2.1.1.6.0',
    entClass => '1.3.6.1.2.1.47.1.1.1.1.5', entDescr => '1.3.6.1.2.1.47.1.1.1.1.2', entSerial => '1.3.6.1.2.1.47.1.1.1.1.11',
    entMfg => '1.3.6.1.2.1.47.1.1.1.1.12', entModel => '1.3.6.1.2.1.47.1.1.1.1.13', entName => '1.3.6.1.2.1.47.1.1.1.1.7',
);

# "version:2c,community:x" lines (or ';'-separated) -> list of hashes
sub parse_credentials {
    my ($text) = @_;
    my @out;
    for my $line (split /[\n;]/, $text // '') {
        $line =~ s/\s+#.*$//;
        $line =~ s/^\s+|\s+$//g;
        next if $line eq '' || $line =~ /^#/;
        my %c = map { my ($k, $v) = split /:/, $_, 2; (lc $k => $v // '') } split /,/, $line;
        push @out, \%c if $c{version};
    }
    return @out;
}

sub session {
    my ($ip, $c, $timeout) = @_;
    my %o = (-hostname => $ip, -timeout => $timeout || 2, -retries => 1, -maxmsgsize => 65535, -translate => [-octetstring => 0]);
    if (($c->{version} // '') eq '3') {
        %o = (%o, -version => 'snmpv3', -username => $c->{username});
        if ($c->{authpassword}) { $o{-authprotocol} = lc($c->{authprotocol} || 'md5'); $o{-authpassword} = $c->{authpassword} }
        if ($c->{privpassword}) { $o{-privprotocol} = lc($c->{privprotocol} || 'des'); $o{-privpassword} = $c->{privpassword} }
    } else {
        %o = (%o, -version => ($c->{version} eq '1' ? 'snmpv1' : 'snmpv2c'), -community => $c->{community} || 'public');
    }
    return Net::SNMP->session(%o);
}

sub text {   # printable text from an OCTET STRING (hex-coded values are dropped)
    my $v = shift // '';
    return '' if $v =~ /[\x00-\x08\x0e-\x1f]/;
    $v =~ s/[\r\n\t]+/ /g;
    $v =~ s/^\s+|\s+$//g;
    return $v;
}

sub label {   # "version 2c, community d***" for messages, no secrets
    my $c = shift;
    return $c->{version} eq '3' ? "v3 user $c->{username}" : "v$c->{version} community " . substr($c->{community} // '', 0, 1) . '***';
}

# Facts about $ip using the first credential that answers.
# Returns (\%facts, \@attempts); facts empty when no credential answered.
sub probe {
    my ($ip, $creds, $timeout) = @_;
    my (@tried, %f);
    for my $i (0 .. $#$creds) {
        my $c = $creds->[$i];
        my ($s, $err) = session($ip, $c, $timeout);
        unless ($s) { push @tried, { credential => $i + 1, label => label($c), ok => 0, error => $err }; next }
        my $r = $s->get_request(-varbindlist => [ @O{qw(sysDescr sysObjectID sysName sysLocation)} ]);
        unless ($r) {
            push @tried, { credential => $i + 1, label => label($c), ok => 0, error => $s->error };
            $s->close;
            next;
        }
        push @tried, { credential => $i + 1, label => label($c), ok => 1 };
        $f{credential} = $i + 1;
        $f{description} = text($r->{ $O{sysDescr} });
        $f{name} = text($r->{ $O{sysName} });
        $f{sys_location} = text($r->{ $O{sysLocation} });
        my $oid = ($r->{ $O{sysObjectID} } // '') =~ s/^\.//r;
        $f{sysobjectid} = $oid;
        if ($oid =~ /^1\.3\.6\.1\.4\.1\.(\d+)/) { $f{manufacturer} = $ENTERPRISE{$1} // '' }
        entity($s, \%f);
        vendor($s, \%f) unless $f{model} && $f{serial};
        $s->close;
        last;
    }
    return (\%f, \@tried);
}

# Vendor MIBs for devices without (useful) ENTITY-MIB: enterprise => [model OID, serial OID]
my %VENDOR_OIDS = (
    232   => [ '1.3.6.1.4.1.232.2.2.4.2.0', '1.3.6.1.4.1.232.2.2.2.1.0' ],          # HPE iLO: product name, serial
    674   => [ '1.3.6.1.4.1.674.10892.5.1.3.12.0', '1.3.6.1.4.1.674.10892.5.1.3.2.0' ],  # Dell iDRAC: model, service tag
    318   => [ '1.3.6.1.4.1.318.1.1.1.1.1.1.0', '1.3.6.1.4.1.318.1.1.1.1.2.3.0' ],  # APC UPS
    12356 => [ undef, '1.3.6.1.4.1.12356.100.1.1.1.0' ],                            # Fortinet: serial
    25461 => [ '1.3.6.1.4.1.25461.2.1.2.2.1.0', '1.3.6.1.4.1.25461.2.1.2.1.3.0' ],  # Palo Alto
);
my @APC_PDU = ('1.3.6.1.4.1.318.1.1.12.1.5.0', '1.3.6.1.4.1.318.1.1.12.1.6.0');      # APC rack PDU: model, serial

sub vendor {
    my ($s, $f) = @_;
    my ($ent) = ($f->{sysobjectid} // '') =~ /^1\.3\.6\.1\.4\.1\.(\d+)/ or return;
    my @try = $VENDOR_OIDS{$ent} ? ($VENDOR_OIDS{$ent}) : ();
    push @try, \@APC_PDU if $ent == 318;
    for my $pair (@try) {
        my @oids = grep { defined } @$pair;
        my $r = $s->get_request(-varbindlist => \@oids) or next;
        my ($m, $n) = map { defined $_ ? text($r->{$_}) : '' } @$pair;
        $m = '' if $m =~ /noSuch/i;
        $n = '' if $n =~ /noSuch/i;
        $f->{model} //= $m if length $m;
        $f->{serial} //= $n if length $n;
        last if $f->{model} && $f->{serial};
    }
}

# ENTITY-MIB: the chassis (class 3) is the device itself; else the first
# entry with a serial number
sub entity {
    my ($s, $f) = @_;
    my %t;
    for my $col (qw(entClass entSerial entModel entMfg entDescr)) {
        my $r = $s->get_table(-baseoid => $O{$col}, -maxrepetitions => 20) or next;
        while (my ($k, $v) = each %$r) { my ($idx) = $k =~ /\.(\d+)$/; $t{$idx}{$col} = $v }
    }
    return unless %t;
    my @idx = sort { $a <=> $b } keys %t;
    my ($pick) = grep { ($t{$_}{entClass} // 0) == 3 && length text($t{$_}{entSerial}) } @idx;
    ($pick) = grep { ($t{$_}{entClass} // 0) == 3 } @idx unless defined $pick;
    ($pick) = grep { length text($t{$_}{entSerial}) } @idx unless defined $pick;
    return unless defined $pick;
    my $e = $t{$pick};
    $f->{serial} = text($e->{entSerial}) if length text($e->{entSerial});
    my $model = text($e->{entModel});
    $model = text($e->{entDescr}) if !length $model && length text($e->{entDescr}) < 60;
    $f->{model} = $model if length $model;
    $f->{manufacturer} = text($e->{entMfg}) if length text($e->{entMfg});
}

1;
