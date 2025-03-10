#!/bin/sh

XDG_RUNTIME_DIR=/run/user/$(id -u)
CONFIGDIR=$HOME/.config
MPVDIR=$CONFIGDIR/mpv
export XDG_RUNTIME_DIR

MPVDIR=$HOME/.config/mpv
SOURCEDIR=$(dirname $(realpath $0))/mpv

if [ ! -d ${MPVDIR} ]; then
	mkdir -p $MPVDIR
	cp -r $SOURCEDIR/* $MPVDIR/
fi

SCRIPTPATH=$(dirname $(realpath $0))
if [ -f $SCRIPTPATH/launch_KlipperScreen.sh ]
then
echo "Running $SCRIPTPATH/launch_KlipperScreen.sh"
$SCRIPTPATH/launch_KlipperScreen.sh
exit $?
fi

if [[ "$BACKEND" =~ ^[wW]$ ]]; then
    echo "Running KlipperScreen on Cage"
    /usr/bin/cage -ds $KS_XCLIENT

else
    echo "Running KlipperScreen on X in display :0 by default"
    /usr/bin/xinit $KS_XCLIENT
fi
