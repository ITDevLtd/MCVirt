#!/bin/bash

set -e

echo () {
	/bin/echo
	/bin/echo ==========================================================
	/bin/echo $@
	/bin/echo ==========================================================
}

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

TEMP_DIR=`mktemp -d`
pushd $TEMP_DIR

	echo Checking for Python PIP...
	which pip || apt-get install --assume-yes python-pip

	if [ "x$SOURCE_PATH" != "x" ]
	then
	    cp -r $SOURCE_PATH ./
	    push $SOURCE_PATH
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
	dpkg -i mcvirt{,-common,-daemon}_${RELEASE}-*.deb

	echo Installing pre-requisites
	apt-get install -f

popd
rm -rf $TEMP_DIR
