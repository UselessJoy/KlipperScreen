#!/bin/bash

SCRIPTPATH=$(dirname -- "$(readlink -f -- "$0")")
KSPATH=$(dirname "$SCRIPTPATH")
KSENV="${KLIPPERSCREEN_VENV:-${HOME}/.KlipperScreen-env}"

# Обновленные пакеты для РЕД ОС
XSERVER="xorg-x11-xinit xorg-x11-server-utils xorg-x11-drv-evdev xorg-x11-drv-libinput xorg-x11-server-Xorg xorg-x11-drv-fbdev"
CAGE="cage seatd xorg-x11-server-Xwayland"
PYTHON="python3-virtualenv python3-libs python3-setuptools"
PYGOBJECT="gobject-introspection-devel gcc cairo-devel pkgconf-pkg-config python3-devel gtk3-devel"
MISC="librsvg2 openjpeg2 wireless-tools dbus-glib-devel autoconf"
OPTIONAL="google-nanum-fonts vlgothic-fonts mpv-devel polkit NetworkManager chrony"

Red='\033[0;31m'
Green='\033[0;32m'
Cyan='\033[0;36m'
Normal='\033[0m'

echo_text ()
{
    printf "${Normal}$1${Cyan}\n"
}

echo_error ()
{
    printf "${Red}$1${Normal}\n"
}

echo_ok ()
{
    printf "${Green}$1${Normal}\n"
}

install_graphical_backend()
{
  while true; do
    if [ -z "$BACKEND" ]; then
      echo_ok "Default is Xserver"
      echo_text "Wayland is EXPERIMENTAL needs kms/drm drivers doesn't support DPMS and may need autologin"
      read -r -e -p "Backend Xserver or Wayland (cage)? [X/w]" BACKEND
      if [[ "$BACKEND" =~ ^[wW]$ ]]; then
        echo_text "Installing Wayland Cage Kiosk"
        if sudo dnf install -y $CAGE; then
            echo_ok "Installed Cage"
            BACKEND="W"
            break
        else
            echo_error "Installation of Cage dependencies failed ($CAGE)"
            exit 1
        fi
      else
        echo_text "Installing Xserver"
        if sudo dnf install -y $XSERVER; then
            echo_ok "Installed X"
            update_x11
            BACKEND="X"
            break
        else
            echo_error "Installation of X-server dependencies failed ($XSERVER)"
            exit 1
        fi
      fi
    fi
  done
}

install_packages()
{
    echo_text "Update package data"
    sudo dnf makecache

    echo_text "Installing KlipperScreen dependencies"
    sudo dnf install -y $OPTIONAL
    echo "$_"
    if sudo dnf install -y $PYTHON; then
        echo_ok "Installed Python dependencies"
    else
        echo_error "Installation of Python dependencies failed ($PYTHON)"
        exit 1
    fi
    if sudo dnf install -y $PYGOBJECT; then
        echo_ok "Installed PyGobject dependencies"
    else
        echo_error "Installation of PyGobject dependencies failed ($PYGOBJECT)"
        exit 1
    fi
    if sudo dnf install -y $MISC; then
        echo_ok "Installed Misc packages"
    else
        echo_error "Installation of Misc packages failed ($MISC)"
        exit 1
    fi
}

check_requirements()
{
    echo_text "Checking Python version"
    python3 --version
    if ! python3 -c 'import sys; exit(1) if sys.version_info <= (3,7) else exit(0)'; then
        echo_text 'Not supported'
        exit 1
    fi
}

create_virtualenv()
{
    echo_text "Creating virtual environment"
    if [ ! -d ${KSENV} ]; then
        virtualenv -p /usr/bin/python3 ${KSENV}
    fi

    source ${KSENV}/bin/activate
    pip --disable-pip-version-check install -r ${KSPATH}/scripts/KlipperScreen-requirements.txt
    
    # Для ARM-систем используем piwheels
    if [[ "$(uname -m)" =~ armv[67]l ]]; then
        echo_text "Using armv[67]l! Adding piwheels.org as extra index..."
        pip --disable-pip-version-check install --extra-index-url https://www.piwheels.org/simple -r ${KSPATH}/scripts/KlipperScreen-requirements.txt
    else
        pip --disable-pip-version-check install -r ${KSPATH}/scripts/KlipperScreen-requirements.txt
    fi
    
    if [ $? -gt 0 ]; then
        echo_error "Error: pip install exited with status code $?"
        echo_text "Trying again with new tools..."
        sudo dnf install -y gcc cmake make
        pip install --upgrade pip setuptools
        pip install -r ${KSPATH}/scripts/KlipperScreen-requirements.txt
        if [ $? -gt 0 ]; then
            echo_error "Unable to install dependencies, aborting install."
            deactivate
            exit 1
        fi
    fi
    deactivate
    echo_ok "Virtual enviroment created"
}

install_systemd_service()
{
    echo_text "Installing KlipperScreen unit file"

    SERVICE=$(cat "$SCRIPTPATH"/KlipperScreen.service)
    SERVICE=${SERVICE//KS_USER/$USER}
    SERVICE=${SERVICE//KS_ENV/$KSENV}
    SERVICE=${SERVICE//KS_DIR/$KSPATH}
    SERVICE=${SERVICE//KS_BACKEND/$BACKEND}

    echo "$SERVICE" | sudo tee /etc/systemd/system/KlipperScreen.service > /dev/null
    sudo systemctl unmask KlipperScreen.service
    sudo systemctl daemon-reload
    sudo systemctl enable KlipperScreen
    sudo systemctl set-default multi-user.target
    sudo usermod -aG tty "$USER"
}

create_policy()
{
    POLKIT_DIR="/etc/polkit-1/rules.d"
    POLKIT_USR_DIR="/usr/share/polkit-1/rules.d"

    echo_text "Installing KlipperScreen PolicyKit Rules"
    sudo groupadd -f klipperscreen
    sudo usermod -aG netdev "$USER"
    if [ ! -x "$(command -v pkaction)" ]; then
        echo "PolicyKit not installed"
        return
    fi

    POLKIT_VERSION="$( pkaction --version | grep -Po "(\d+\.?\d*)" )"
    echo_text "PolicyKit Version ${POLKIT_VERSION} Detected"
    if [ "$POLKIT_VERSION" = "0.105" ]; then
        # install legacy pkla
        create_policy_legacy
        return
    fi

    RULE_FILE=""
    if [ -d $POLKIT_USR_DIR ]; then
        RULE_FILE="${POLKIT_USR_DIR}/KlipperScreen.rules"
    elif [ -d $POLKIT_DIR ]; then
        RULE_FILE="${POLKIT_DIR}/KlipperScreen.rules"
    else
        echo "PolicyKit rules folder not detected"
        exit 1
    fi
    echo_text "Installing PolicyKit Rules to ${RULE_FILE}..."

    KS_GID=$( getent group klipperscreen | awk -F: '{printf "%d", $3}' )
    sudo /bin/sh -c "cat > ${RULE_FILE}" << EOF
// Allow KlipperScreen to reboot, shutdown, etc
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.power-off-multiple-sessions" ||
         action.id == "org.freedesktop.login1.reboot" ||
         action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
         action.id == "org.freedesktop.login1.halt" ||
         action.id == "org.freedesktop.login1.halt-multiple-sessions" ||
         action.id.startsWith("org.freedesktop.NetworkManager.")) &&
        subject.user == "$USER") {
        // Only allow processes with the "klipperscreen" supplementary group
        // access
        var regex = "^Groups:.+?\\\s$KS_GID[\\\s\\\0]";
        var cmdpath = "/proc/" + subject.pid.toString() + "/status";
        try {
            polkit.spawn(["grep", "-Po", regex, cmdpath]);
            return polkit.Result.YES;
        } catch (error) {
            return polkit.Result.NOT_HANDLED;
        }
    }
});
EOF
}

create_policy_legacy()
{
    RULE_FILE="/etc/polkit-1/localauthority/50-local.d/20-klipperscreen.pkla"
    sudo tee ${RULE_FILE} > /dev/null << EOF
[KlipperScreen]
Identity=unix-user:$USER
Action=org.freedesktop.login1.power-off;
       org.freedesktop.login1.power-off-multiple-sessions;
       org.freedesktop.login1.reboot;
       org.freedesktop.login1.reboot-multiple-sessions;
       org.freedesktop.login1.halt;
       org.freedesktop.login1.halt-multiple-sessions;
       org.freedesktop.NetworkManager.*
ResultAny=yes
EOF
}

update_x11()
{
    sudo tee /etc/X11/Xwrapper.config > /dev/null << EOF
allowed_users=anybody
needs_root_rights=yes
EOF
}

fix_fbturbo()
{
    # Не требуется для РЕД ОС
    return
}

add_desktop_file()
{
    mkdir -p "$HOME"/.local/share/applications/
    cp "$SCRIPTPATH"/KlipperScreen.desktop "$HOME"/.local/share/applications/KlipperScreen.desktop
    sudo cp "$SCRIPTPATH"/../styles/icon.svg /usr/share/icons/hicolor/scalable/apps/KlipperScreen.svg
}

start_KlipperScreen()
{
    echo_text "Starting service..."
    sudo systemctl restart KlipperScreen
}


# Script start
if [ "$EUID" == 0 ]
    then echo_error "Please do not run this script as root"
    exit 1
fi

# Включение EPEL репозитория
if ! rpm -q epel-release; then
    echo_text "Enabling EPEL repository..."
    sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
    sudo dnf config-manager --set-enabled powertools
fi

check_requirements
if [ -z "$SERVICE" ]; then
    read -r -e -p "Install as a service? (This will enable boot to console) [Y/n]" SERVICE
    if [[ $SERVICE =~ ^[nN]$ ]]; then
        echo_text "Not installing the service"
        echo_text "The graphical backend will NOT be installed"
    else
        install_graphical_backend
        install_systemd_service
        if [ -z "$START" ]; then
            START=1
        fi
    fi
fi

install_packages
create_virtualenv
create_policy
fix_fbturbo
add_desktop_file
if [ -z "$START" ] || [ "$START" -eq 0 ]; then
    echo_ok "KlipperScreen was installed"
else
    start_KlipperScreen
fi