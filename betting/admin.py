from django import forms
from django.contrib import admin
from betting.models import Evento, Mercado, Seleccion, Apuesta, Equipo


class MercadoForm(forms.ModelForm):
    NOMBRES_MERCADOS = [
        ("1X2", "1X2"),
        ("Doble Oportunidad", "Doble Oportunidad"),
        ("Más/Menos 2.5", "Más/Menos 2.5"),
        ("Ambos Equipos Anotan", "Ambos Equipos Anotan"),
    ]
    nombre = forms.ChoiceField(choices=NOMBRES_MERCADOS, label="Mercado")

    class Meta:
        model = Mercado
        fields = ["nombre", "activo"]


class MercadoInline(admin.TabularInline):
    model = Mercado
    form = MercadoForm
    extra = 1


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["id", "local", "visitante", "fecha_inicio", "estado", "goles_local", "goles_visitante"]
    list_filter = ["estado", "fecha_inicio"]
    search_fields = ["local", "visitante"]
    inlines = [MercadoInline]


class SeleccionInline(admin.TabularInline):
    model = Seleccion
    extra = 3


@admin.register(Mercado)
class MercadoAdmin(admin.ModelAdmin):
    form = MercadoForm
    list_display = ["id", "nombre", "evento", "activo"]
    list_filter = ["activo"]
    inlines = [SeleccionInline]


@admin.register(Seleccion)
class SeleccionAdmin(admin.ModelAdmin):
    list_display = ["id", "nombre", "cuota", "mercado"]
    search_fields = ["nombre"]


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ["id", "nombre"]
    search_fields = ["nombre"]


@admin.register(Apuesta)
class ApuestaAdmin(admin.ModelAdmin):
    list_display = ["id", "usuario", "seleccion", "monto", "cuota_fijada", "estado", "creado"]
    list_filter = ["estado", "creado"]
    search_fields = ["usuario__username"]
