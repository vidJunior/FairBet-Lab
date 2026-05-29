from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from betting.models import Equipo, Evento, Mercado, Seleccion
from config.choices import EstadoEvento
from betting.services import crear_mercados_para_evento

class Command(BaseCommand):
    help = "Populates the database with scheduled matches (partidos programados) for testing."

    def handle(self, *args, **options):
        self.stdout.write("Sembrando equipos y partidos programados...")

        # Lista de equipos
        nombres_equipos = [
            "Real Madrid", "Barcelona", "Manchester City", "Liverpool",
            "Bayern Munich", "PSG", "Juventus", "AC Milan",
            "Arsenal", "Chelsea", "Atletico Madrid", "Dortmund"
        ]

        equipos = {}
        for nombre in nombres_equipos:
            equipo, created = Equipo.objects.get_or_create(nombre=nombre)
            equipos[nombre] = equipo
            if created:
                self.stdout.write(f"Equipo creado: {nombre}")

        # Definir partidos programados
        ahora = timezone.now()
        partidos_data = [
            {
                "local": "Real Madrid",
                "visitante": "Barcelona",
                "fecha_inicio": ahora + timedelta(days=1, hours=15), # Mañana
                "cuotas": {"Local": "2.1000", "Empate": "3.6000", "Visitante": "3.2000"}
            },
            {
                "local": "Manchester City",
                "visitante": "Liverpool",
                "fecha_inicio": ahora + timedelta(days=2, hours=12), # Pasado mañana
                "cuotas": {"Local": "1.9500", "Empate": "3.7500", "Visitante": "3.5000"}
            },
            {
                "local": "Bayern Munich",
                "visitante": "Dortmund",
                "fecha_inicio": ahora + timedelta(days=3, hours=10),
                "cuotas": {"Local": "1.6500", "Empate": "4.2000", "Visitante": "4.8000"}
            },
            {
                "local": "Arsenal",
                "visitante": "Chelsea",
                "fecha_inicio": ahora + timedelta(days=4, hours=14),
                "cuotas": {"Local": "1.8000", "Empate": "3.5000", "Visitante": "4.2000"}
            },
            {
                "local": "Juventus",
                "visitante": "AC Milan",
                "fecha_inicio": ahora + timedelta(days=5, hours=19),
                "cuotas": {"Local": "2.2000", "Empate": "3.1000", "Visitante": "3.4000"}
            },
            {
                "local": "PSG",
                "visitante": "Atletico Madrid",
                "fecha_inicio": ahora + timedelta(days=6, hours=18),
                "cuotas": {"Local": "1.7500", "Empate": "3.8000", "Visitante": "4.5000"}
            }
        ]

        # Limpiar eventos programados viejos para evitar duplicados
        deleted_count, _ = Evento.objects.filter(estado=EstadoEvento.PROGRAMADO).delete()
        self.stdout.write(f"Se eliminaron {deleted_count} eventos programados antiguos.")

        for p in partidos_data:
            elocal = equipos[p["local"]]
            evisitante = equipos[p["visitante"]]
            
            # get_or_create para evitar duplicados
            evento, created = Evento.objects.get_or_create(
                local=p["local"],
                visitante=p["visitante"],
                fecha_inicio=p["fecha_inicio"],
                defaults={
                    "local_equipo": elocal,
                    "visitante_equipo": evisitante,
                    "estado": EstadoEvento.PROGRAMADO,
                    "goles_local": 0,
                    "goles_visitante": 0,
                    "minuto_actual": 0,
                    "periodo": "1T"
                }
            )

            # Crear todos los mercados por defecto usando el service oficial (1X2, Doble Op, Más/Menos, BTTS)
            crear_mercados_para_evento(evento)
            self.stdout.write(f"Mercados premium creados/verificados para: {evento}")

            # Actualizar cuotas personalizadas del mercado 1X2 si es necesario
            mercado_1x2 = evento.mercados.filter(nombre="1X2").first()
            if mercado_1x2:
                for nombre_sel, valor_cuota in p["cuotas"].items():
                    seleccion = mercado_1x2.selecciones.filter(nombre__iexact=nombre_sel).first()
                    if seleccion:
                        seleccion.cuota = Decimal(valor_cuota)
                        seleccion.save()
                        self.stdout.write(f"  Cuota 1X2 ajustada: {nombre_sel} -> {valor_cuota}")

        self.stdout.write(self.style.SUCCESS("Base de datos sembrada con TODOS los mercados con éxito!"))

