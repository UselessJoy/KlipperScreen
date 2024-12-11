class KlippyGcodes:
    HOME = "G28"
    HOME_XY = "G28 X Y"
    HOME_X = "G28 X"
    HOME_Y = "G28 Y"
    HOME_Z = "G28 Z"
    Z_TILT = "Z_TILT_ADJUST"
    QUAD_GANTRY_LEVEL = "QUAD_GANTRY_LEVEL"

    MOVE = "G1"
    MOVE_ABSOLUTE = "G90"
    MOVE_RELATIVE = "G91"

    EXTRUDE_ABS = "M82"
    EXTRUDE_REL = "M83"

    SET_EXT_TEMP = "M104"
    SET_BED_TEMP = "M140"

    SET_EXT_FACTOR = "M221"
    SET_FAN_SPEED = "M106"
    SET_SPD_FACTOR = "M220"

    PROBE_CALIBRATE = "PROBE_CALIBRATE SAMPLES=4"
    Z_ENDSTOP_CALIBRATE = "Z_ENDSTOP_CALIBRATE"
    TESTZ = "TESTZ Z="
    ABORT = "ABORT"
    ACCEPT = "ACCEPT"
    
    
    @staticmethod
    def set_led_color(led, color):
        return (
            f'SET_LED LED="{led}" '
            f'RED={color[0]} GREEN={color[1]} BLUE={color[2]} WHITE={color[3]} '
            f'SYNC=0 TRANSMIT=1'
        )
        
    @staticmethod
    def set_bed_temp(temp):
        return f"M140 S{temp}"

    @staticmethod
    def set_ext_temp(temp, tool=0):
        return f"M104 T{tool} S{temp}"

    @staticmethod
    def set_heater_temp(heater, temp):
        return f'SET_HEATER_TEMPERATURE heater="{heater}" target={temp}'

    @staticmethod
    def set_temp_fan_temp(temp_fan, temp):
        return f'SET_TEMPERATURE_FAN_TARGET temperature_fan="{temp_fan}" target={temp}'

    @staticmethod
    def set_fan_speed(speed):
        return f"{KlippyGcodes.SET_FAN_SPEED} S{speed * 2.55:.0f}"

    @staticmethod
    def set_extrusion_rate(rate):
        return f"M221 S{rate}"

    @staticmethod
    def set_speed_rate(rate):
        return f"{KlippyGcodes.SET_SPD_FACTOR} S{rate}"

    @staticmethod
    def testz_move(dist):
        return KlippyGcodes.TESTZ + dist

    @staticmethod
    def extrude(dist, speed=500):
        return f"{KlippyGcodes.MOVE} E{dist} F{speed}"

    @staticmethod
    def bed_mesh_load(profile):
        return f"BED_MESH_PROFILE LOAD='{profile}'"

    @staticmethod
    def bed_mesh_remove(profile):
        return f"BED_MESH_PROFILE REMOVE='{profile}'"

    @staticmethod
    def bed_mesh_save(profile):
        return f"BED_MESH_PROFILE SAVE='{profile}'"
    
    ####      NEW      ####
    @staticmethod
    def set_led(name, r, g, b):
        return f"SET_LED LED={name} RED={r} GREEN={g} BLUE={b}"
    
    @staticmethod
    def save_default_neopixel_color(name, r, g, b):
        return f"SAVE_DEFAULT_COLOR NEOPIXEL={name} RED={r} GREEN={g} BLUE={b}"
    
    @staticmethod
    def turn_off_led():
        return f"DISABLE_LED_EFFECTS"

    @staticmethod
    def turn_on_led():
        return f"ENABLE_LED_EFFECTS"
    
    @staticmethod
    def pass_interrupt():
        return f"SDCARD_PASS_FILE"
    
    @staticmethod
    def get_magnet_probe():
        return f"GET_MAGNET_PROBE"
    
    @staticmethod
    def return_magnet_probe():
        return f"RETURN_MAGNET_PROBE"
    ####    END NEW    ####
