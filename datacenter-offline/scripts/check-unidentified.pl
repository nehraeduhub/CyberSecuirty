#!/usr/bin/perl
# Probe addresses that GLPI lists as unidentified (Unmanaged): SNMP with each
# configured credential (and "public"), a few TCP ports and the SSH banner,
# then guess what the device is and how to collect it.
# Runs inside the collector container (Net::SNMP), see check-unidentified.sh.
#
#   perl check-unidentified.pl <credentials separated by ';'>   (reads "ip<TAB>mac" lines on stdin)
use strict;
use warnings;
use Net::SNMP;
use IO::Socket::INET;

my ($credlist) = @ARGV;
my @creds = map {
    my %c = map { my ($k, $v) = split /:/, $_, 2; (lc $k => $v // '') } split /,/, $_;
    \%c
} grep { /version:/ } split /;/, $credlist // '';
push @creds, { version => '2c', community => 'public', _default => 1 };

my %PORTS = (22 => 'ssh', 80 => 'http', 443 => 'https', 902 => 'vmware', 3389 => 'rdp', 5985 => 'winrm');

sub snmp_try {
    my ($ip, $c) = @_;
    my %o = (-hostname => $ip, -timeout => 2, -retries => 0);
    if (($c->{version} // '') eq '3') {
        %o = (%o, -version => 'snmpv3', -username => $c->{username});
        if ($c->{authpassword}) { $o{-authprotocol} = lc($c->{authprotocol} || 'md5'); $o{-authpassword} = $c->{authpassword} }
        if ($c->{privpassword}) { $o{-privprotocol} = lc($c->{privprotocol} || 'des'); $o{-privpassword} = $c->{privpassword} }
    } else {
        %o = (%o, -version => ($c->{version} eq '1' ? 'snmpv1' : 'snmpv2c'), -community => $c->{community} || 'public');
    }
    my ($s, $err) = Net::SNMP->session(%o);
    unless ($s) { warn "SNMP setup: $err\n" if $err && $err !~ /No response|discovery/i; return }
    my $r = $s->get_request(-varbindlist => ['1.3.6.1.2.1.1.1.0']);
    $s->close;
    return $r ? ($r->{'1.3.6.1.2.1.1.1.0'} // '') : undef;
}

sub tcp_open {
    my ($ip, $port) = @_;
    my $sock = IO::Socket::INET->new(PeerAddr => $ip, PeerPort => $port, Proto => 'tcp', Timeout => 2) or return;
    my $banner = '';
    if ($port == 22) {
        my $rin = ''; vec($rin, fileno($sock), 1) = 1;
        if (select($rin, undef, undef, 3)) { sysread($sock, $banner, 200); $banner =~ s/[\r\n].*//s }
    }
    close $sock;
    return $banner || 1;
}

while (my $line = <STDIN>) {
    chomp $line;
    my ($ip, $mac) = split /\t/, $line;
    next unless $ip && $ip =~ /^\d+\.\d+\.\d+\.\d+$/;
    my (@open, $ssh);
    for my $p (sort { $a <=> $b } keys %PORTS) {
        my $r = tcp_open($ip, $p) or next;
        push @open, $PORTS{$p};
        $ssh = $r if $p == 22 && $r ne '1';
    }
    my ($snmp, $how);
    for my $c (@creds) {
        my $d = snmp_try($ip, $c);
        next unless defined $d;
        ($snmp, $how) = ($d, $c->{_default} ? 'public' : 'yours');
        last;
    }
    my %o = map { $_ => 1 } @open;
    my $b = $ssh // '';
    my ($what, $todo);
    if ($snmp && $how eq 'yours') {
        ($what, $todo) = ('answers SNMP with your credentials', 'collect again; if it stays unidentified, GLPI refused it because it reports no serial or MAC (see docker compose logs collector), so add it in GLPI by hand');
    } elsif ($snmp) {
        ($what, $todo) = ('answers SNMP community "public"', 'set your own read-only community on it, or add version:2c,community:public to SNMP_CREDENTIALS');
    } elsif ($o{vmware}) {
        ($what, $todo) = ('VMware ESXi host', "add it (or its vCenter) to ESX_HOSTS: $ip <user> <password>");
    } elsif ($o{winrm} || $o{rdp}) {
        ($what, $todo) = ('Windows server', "add to REMOTES: winrm://inventory:PASSWORD\@$ip" . ($o{winrm} ? '' : '  (enable WinRM first: winrm quickconfig)'));
    } elsif ($b =~ /OpenSSH.*(Ubuntu|Debian|el\d|Red ?Hat|Rocky|Alma|SUSE)|OpenSSH_\d/i && $b !~ /Cisco|RomSShell|Comware|Dell|Force10|Aruba|Sophos/i) {
        ($what, $todo) = ('Linux/Unix server (or appliance) with SSH', "add to REMOTES: ssh://inventory\@$ip  (and authorise collector/ssh/id_ed25519.pub on it)");
    } elsif ($b =~ /Cisco|Comware|Force10|Aruba|ProCurve|Dell|HP|Sophos|Alteon|RomSShell|mpSSH/i) {
        ($what, $todo) = ("network device or management card ($b)", 'enable read-only SNMP on it and allow this server, see EQUIPMENT.md');
    } elsif ($o{https} || $o{http}) {
        ($what, $todo) = ('web-managed device (appliance, iLO/iDRAC, PDU, UPS, printer, camera)', 'enable read-only SNMP on it and allow this server, see EQUIPMENT.md');
    } elsif (@open) {
        ($what, $todo) = ('device with SSH only', 'enable SNMP (network device) or add to REMOTES as ssh:// (server)');
    } else {
        ($what, $todo) = ('answers ping only', 'enable SNMP and allow this server in its SNMP access list; or it is a PC/phone you can ignore');
    }
    printf "%s\t%s\t%s\t%s\t%s\t%s\n", $ip, $mac || '-', join(',', @open) || '-', $b || '-', $what, $todo;
}
