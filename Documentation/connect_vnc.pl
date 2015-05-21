#!/usr/bin/perl

use strict;
use warnings;

use Term::ReadKey;
use Net::SSH::Expect;
use Net::OpenSSH;
use Socket;

# Determines if a given port is free on the local machine
sub port_available
{
  my $port = shift;

  socket(my $sock, PF_INET, SOCK_STREAM, getprotobyname('tcp'));
  my $name = sockaddr_in($port, INADDR_ANY);

  bind($sock, $name) and return 1;
}

# Script to connect to VNC display of a VM hosted on an MCVirt host.
#  * Two SSH connections are created:
#    * One to determine the port on which the VNC session is being hosted.
#    * The second forwards a local port to connect to the VNC server,
#      as it is only hosted on the loopback interface of the host.
#  * Whilst the second SSH sessoin is open, a vncviewer is started to
#    connect to the VNC console of the VM

# Obtain the VM name from the first argument and, optionally, MCVirt host from second
my $vm_name = shift || die 'Must provide VM name as first parameter';
my $mcvirt_host = shift || die 'Must specify MCVirt node as second parameter';

# Get username and password from user
my $local_user = getlogin;
print "Username [$local_user]: ";
chomp(my $username = <STDIN>);

# If no username was provided, use local user
$username = $username || $local_user;

# Get password from user
print 'Password: ';
ReadMode('noecho');
chomp(my $password = <STDIN>);
ReadMode(0);
print "\n";

# Login to host to determine vnc display
print "Obtaining VNC details\n";
my $ssh = Net::OpenSSH->new("$username:$password\@$mcvirt_host");

$ssh->error and die "Couldn't establish SSH connection: ". $ssh->error;

my $out = $ssh->capture("sudo mcvirt info --vnc-port $vm_name");

if ($ssh->error())
{
  die $out
}

my $vnc_port = $out;

chomp($vnc_port);

undef($ssh);

print "Locating free local port";
my $local_port = 1231;

my $port_free = 0;
while (! $port_free)
{
  $local_port ++;
  if (port_available($local_port))
  {
    $port_free = 1;
  }
  print '.';
}
print "\n";


print "Reconnecting to forward port\n";
my $port_mapping_option = "-L $local_port:127.0.0.1:$vnc_port";
my $ssh_port_forward = Net::SSH::Expect->new
(
  host => $mcvirt_host,
  password => $password,
  user => $username,
  ssh_option => $port_mapping_option,
  raw_pty => 1,
  timeout => 15
);

$ssh_port_forward->login();

# Launch VNC session
print "Launching VNC session...\n";
`vncviewer 127.0.0.1:$local_port > /dev/null 2>&1`;

# Close SSH session
$ssh_port_forward->close();
