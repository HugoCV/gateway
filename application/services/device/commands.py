class DeviceCommands:
    def __init__(self, log):
        self.log = log

    def turn_on(self, cc, conns):
        mode = cc.get("mode")
        self.log(f"Se mando a ejecutar turn_on (modo={mode})")
        if mode == "remote":
            if self._write_if_connected(conns.tcp, 898, 3, "turn_on TCP"):
                return True
            if self._write_if_connected(conns.serial, 897, 3, "turn_on Serial"):
                return True
        elif mode == "local" and conns.logo:
            return self._call_logo(conns.logo, "turn_on")

        self.log(f"⚠️ No se pudo ejecutar turn_on (modo={mode})")
        return False

    def turn_off(self, cc, conns):
        mode = cc.get("mode")
        if mode == "remote":
            ok = False
            if self._write_if_connected(conns.tcp, 898, 0, "turn_off TCP"):
                ok = True
                self.set_local(conns)
            elif self._write_if_connected(conns.serial, 897, 0, "turn_off Serial"):
                ok = True
                self.set_local(conns)
            return ok
        elif mode == "local" and conns.logo:
            return self._call_logo(conns.logo, "turn_off")

        self.log(f"⚠️ No se pudo ejecutar turn_off (modo={mode})")
        return False

    def restart(self, cc, conns):
        mode = cc.get("mode")
        if mode == "remote":
            if self._restart_sequence(conns.tcp, 901, "TCP"):
                return True
            if self._restart_sequence(conns.serial, 900, "Serial"):
                return True
        elif mode == "local" and conns.logo:
            return self._call_logo(conns.logo, "restart")

        self.log(f"⚠️ No se pudo ejecutar restart (modo={mode})")
        return False

    def set_local(self, conns):
        if self._write_if_connected(conns.serial, 4357, 2, "set_local Serial"):
            return True
        if self._write_if_connected(conns.tcp, 4358, 2, "set_local TCP"):
            return True
        self.log("⚠️ Ninguna conexión disponible para set_local")
        return False

    def set_remote(self, conns):
        if self._write_if_connected(conns.serial, 4357, 3, "set_remote Serial"):
            return True
        if self._write_if_connected(conns.tcp, 4358, 4, "set_remote TCP"):
            return True
        self.log("⚠️ Ninguna conexión disponible para set_remote")
        return False

    # === Helpers ===
    def _write_if_connected(self, conn, address, value, label):
        if not conn or not conn.is_connected():
            return False
        try:
            ok = conn.write_register(address, value)
            if ok:
                self.log(f"✅ {label}: [{address}]={value}")
                return True
            self.log(f"⚠️ {label} falló en write_register")
        except Exception as e:
            self.log(f"❌ {label} falló: {e}")
        return False

    def _restart_sequence(self, conn, addr, label):
        if not conn or not conn.is_connected():
            return False
        try:
            conn.write_register(addr, 1)
            conn.write_register(addr, 0)
            if "Tcp" in type(conn).__name__:
                conn.write_register(898, 2)
            else:
                conn.write_register(897, 3)
            self.log(f"🔄 Restart ejecutado en {label}")
            return True
        except Exception as e:
            self.log(f"❌ Error en restart {label}: {e}")
            return False

    def _call_logo(self, logo, action):
        try:
            if hasattr(logo, action):
                getattr(logo, action)()
                self.log(f"✅ {action} via LOGO")
                return True
            else:
                self.log(f"⚠️ LOGO no implementa {action}")
        except Exception as e:
            self.log(f"❌ Error ejecutando {action} en LOGO: {e}")
        return False