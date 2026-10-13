#!/usr/bin/perl
# Keep Prometheus ping targets in sync with GLPI: every device in GLPI that has
# an IPv4 address becomes a monitored target, labelled with its name, type,
# rack and GLPI id. Writes a Prometheus file_sd JSON file every SYNC_MINUTES.
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
use strict;
use warnings;
use LWP::UserAgent;
use JSON::PP;
use MIME::Base64;

my $base    = ($ENV{GLPI_URL} || 'http://glpi') =~ s{/+$}{}r;
my $public  = ($ENV{GLPI_PUBLIC_URL} || '') =~ s{/+$}{}r;
my $user    = $ENV{GLPI_USER} || 'dc-monitor';
my $pass    = $ENV{GLPI_PASSWORD} // '';
my $out     = $ENV{TARGETS_FILE} || '/targets/glpi.json';
my $every   = ($ENV{SYNC_MINUTES} || 5) * 60;
my @types   = split /\s*,\s*/, ($ENV{MONITOR_TYPES} || 'Computer,NetworkEquipment,PDU,Printer,Phone,Peripheral,Enclosure');
my %exclude = map { lc($_) => 1 } grep { length } split /\s*,\s*/, ($ENV{EXCLUDE_STATES} || '');

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

    @targets = sort { $a->{labels}{name} cmp $b->{labels}{name} } @targets;
    my $tmp = "$out.tmp";
    open my $fh, '>', $tmp or die "write $tmp: $!\n";
    print $fh $json->encode(\@targets);
    close $fh;
    rename $tmp, $out or die "rename $tmp: $!\n";
    return scalar @targets;
}

my $once = grep { $_ eq '--once' } @ARGV;
while (1) {
    my $n = eval { sync_once() };
    if (defined $n) { logmsg("synced $n target(s) from GLPI to $out") }
    else            { logmsg("sync failed: $@") }
    last if $once;
    # Retry soon after a failure (e.g. GLPI still starting), else wait the interval
    sleep(defined $n ? $every : 30);
}
