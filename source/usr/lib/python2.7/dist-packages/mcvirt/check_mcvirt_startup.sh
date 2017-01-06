#!/bin/bash

# Copyright (c) 2017 - I.T. Dev Ltd
#
# This file is part of MCVirt.
#
# MCVirt is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# MCVirt is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MCVirt.  If not, see <http://www.gnu.org/licenses/>

# Checks the status of the MCVirt daemon startup

APP="$1"
PID_FILE="/var/run/${APP}.pid"
LOG_FILE="/var/log/${APP}-startup.log"

if [ "z$APP" == "zmcvirtd" ]
then
    CERT_FILE="/var/lib/mcvirt/$HOSTNAME/ssl/$HOSTNAME/clientcert.pem"
elif [ "z$APP" == "zmcvirt-ns" ]
then
    CERT_FILE="/var/lib/mcvirt/$HOSTNAME/ssl/$HOSTNAME/servercert.pem"
else
    echo 'Must specify app'
    exit 2
fi

if [ ! -f "/var/run/${APP}.pid" ]
then
    exit 1
fi

PID=`cat $PID_FILE`

check_daemon_running() {

    if [ ! -d "/proc/$PID" ]
    then
        return 0
    fi


    if [ "$(cat /proc/`cat $PID_FILE`/comm)" == "$APP" ]
    then
        return 1
    fi
    return 0
}

for i in {1..180}
do
    if check_daemon_running
    then
        echo -e "Daemon failed to start\nCheck the MCVirt log\nor attempt to run mcvirtd manually" >&2
        exit 1
    fi

    if [ -f "$CERT_FILE" ]
    then
        if [ "z$APP" == "zmcvirtd" ]
        then
            exit 0
        else
            # Check to ensure nameserver is listening on port
            /usr/bin/lsof -Pan -p $PID -i | grep :9090 >/dev/null 2>&1
            if [ "$?" == "0" ]
            then
                exit 0
            fi
        fi
    fi

    sleep 1
done

# If for-loop reaches the end, assume that
# something has gone wrong
echo 'Daemon failed to start in timely mannor' >&2
exit 1
