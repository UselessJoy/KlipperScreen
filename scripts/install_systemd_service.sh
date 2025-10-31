#!/bin/bash

detect_password() {
    if command -v apt &> /dev/null; then
        echo "orangepi"
    elif command -v dnf &> /dev/null; then
        echo "user"
    else
        echo "unknown"
    fi
}
pwd=$(detect_password)

echo_text ()
{
    printf "${Normal}$1${Cyan}\n"
}

KSENV="${KLIPPERSCREEN_VENV:-${HOME}/.KlipperScreen-env}"
SCRIPTPATH=$(dirname -- "$(readlink -f -- "$0")")
KSPATH=$(dirname "$SCRIPTPATH")
BACKEND="X"

echo_text "Installing KlipperScreen unit file"
SERVICE=$(cat "$SCRIPTPATH"/KlipperScreen.service)
SERVICE=${SERVICE//KS_USER/$USER}
SERVICE=${SERVICE//KS_ENV/$KSENV}
SERVICE=${SERVICE//KS_DIR/$KSPATH}
SERVICE=${SERVICE//KS_BACKEND/$BACKEND}
# echo "$SERVICE" | echo "$pwd" | sudo -S tee /etc/systemd/system/KlipperScreen.service > /dev/null
# echo "$pwd" | sudo -S systemctl daemon-reload
TEMP_FILE=$(mktemp)
echo "$SERVICE" > "$TEMP_FILE"
echo "$pwd" | sudo -S install -m 644 "$TEMP_FILE" /etc/systemd/system/KlipperScreen.service
rm -f "$TEMP_FILE"
echo "$pwd" | sudo -S systemctl daemon-reload
