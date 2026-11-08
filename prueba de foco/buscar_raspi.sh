#!/bin/bash
# Busca la Raspberry Pi en la red a la que está conectado este Mac.
# Uso:  bash buscar_raspi.sh

OUIS="2c:cf:67|d8:3a:dd|dc:a6:32|e4:5f:1|b8:27:eb|28:cd:c1|88:a2:9e"   # fabricantes Raspberry Pi
USUARIO=alex
encontradas=()

echo "IP de este Mac: $(ipconfig getifaddr en0 2>/dev/null || echo '?')"

# 1) Si estás conectado a una wifi que crea la propia Pi, la Pi es el router.
GW=$(route -n get default 2>/dev/null | awk '/gateway/{print $2}')
echo "Router (puerta de enlace): ${GW:-ninguno}"

# 2) Nombres habituales por mDNS
for n in raspberrypi.local planktoscope.local pkscope.local "$(hostname -s).local"; do
  ip=$(ping -c1 -t2 "$n" 2>/dev/null | sed -n 's/.*(\([0-9.]*\)).*/\1/p' | head -1)
  [ -n "$ip" ] && [ "$n" != "$(hostname -s).local" ] && { echo "  $n -> $ip"; encontradas+=("$ip"); }
done

# 3) Barrido de la subred /24 y búsqueda por fabricante en la tabla ARP
BASE=$(ipconfig getifaddr en0 2>/dev/null | cut -d. -f1-3)
if [ -n "$BASE" ]; then
  echo "Barriendo $BASE.0/24 ..."
  for i in $(seq 1 254); do ping -c1 -W300 "$BASE.$i" >/dev/null 2>&1 & done; wait
fi
while read -r ip; do encontradas+=("$ip"); done < <(arp -an | grep -iE "$OUIS" | sed -n 's/.*(\([0-9.]*\)).*/\1/p')

# 4) ¿El router es la Pi?
if [ -n "$GW" ] && arp -an | grep "($GW)" | grep -qiE "$OUIS"; then encontradas+=("$GW"); fi

echo
if [ ${#encontradas[@]} -eq 0 ]; then
  echo "No se encontró ninguna Raspberry Pi."
  echo "Prueba también la puerta de enlace ($GW) o mira la IP en la propia Pi con:  hostname -I"
else
  for ip in $(printf "%s\n" "${encontradas[@]}" | sort -u); do
    echo "Raspberry Pi probable: $ip"
    echo "   ssh $USUARIO@$ip"
    echo "   navegador (con camara_web.py en marcha): http://$ip:8000"
  done
fi
