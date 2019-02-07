#!/bin/bash

set -e

DEFAULT_ADMIN=mjc
DEFAULT_PASSWORD=password

echo () {
    /bin/echo -e "\n\n=========================================================="
    /bin/echo -e $@
    /bin/echo ==========================================================
}

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# Resolve source path, if set
if [ "x$SOURCE_PATH" != "x" ]
then
    SOURCE_PATH=$(realpath $SOURCE_PATH)
fi

TEMP_DIR=`mktemp -d`
pushd $TEMP_DIR

    echo Checking for Python PIP...
    which pip || apt-get install --assume-yes python-pip

    if [ "x$SOURCE_PATH" != "x" ]
    then
        cp -r $SOURCE_PATH ./
        cd $SOURCE_PATH
    else
        if [ "x$RELEASE" == "x" ]
        then
            echo Checking for curl...
            which curl || apt-get install --assume-yes curl
            RELEASE=$(curl -s https://api.github.com/repos/itdevltd/mcvirt/releases/latest | grep tag_name | sed 's/.*": "//g' | sed 's/".*//g')
        fi

        echo Using release: $RELEASE

        echo Downloading and extracting archive
        curl https://codeload.github.com/ITDevLtd/MCVirt/tar.gz/${RELEASE} -o mcvirt-${RELEASE}.tar.gz
        tar -zxvf mcvirt-${RELEASE}.tar.gz
        cd MCVirt-*
    fi

    echo Installing pyro4...
    pip install ./pyro4

    echo Building package
    ./scripts/build.sh

    echo Installing MCVirt packages
    dpkg -i mcvirt{,-common,-daemon}_*.deb

    echo Installing pre-requisites
    apt-get install -f

popd
rm -rf $TEMP_DIR

echo '(Re)Starting MCVirt Nameserver'
service mcvirt-ns restart

echo '(Re)Starting MCVirt Daemon'
service mcvirtd restart

echo Finished Installation

echo Initial Configuration

read -p "Would you like to perform initial configuration? [y/N]: " CONFIGURE_ANS

if [ "x$CONFIGURE_ANS" == "xy" ]
then
    read -p "Admin username [${DEFAULT_ADMIN}]: " ADMIN_USER
    read -s -p "Admin password [${DEFAULT_PASSWORD}]: " ADMIN_PASSWORD
    /bin/echo

    # Check if username/password are blank and set to default
    if [ "x$ADMIN_USER" == "x" ]
    then
        ADMIN_USER=$DEFAULT_ADMIN
    fi
    if [ "x$ADMIN_PASSWORD" == "x" ]
    then
        ADMIN_PASSWORD=$DEFAULT_PASSWORD
    fi

    if [ "$ADMIN_USER" == "$DEFAULT_ADMIN" ] && [ "$ADMIN_PASSWORD" == "$DEFAULT_PASSWORD" ]
    then
        read -p "Would you like to change the admin username/password? [y/N]: " CHANGE_PWD_ANS
        if [ "x$CHANGE_PWD_ANS" == "xy" ]
        then
            read -s -p 'Enter new password: ' NEW_ADMIN_PASSWORD
            /bin/echo
        fi
    fi
fi

echo Installation/Configuration Complete!

/bin/echo -e "
Default Credentials:
  Username: mjc
  Password: password

Example Command:
  mcvirt list

For further help:
  mcvirt --help
  mcvirt <action> --help
  man mcvirt
"
