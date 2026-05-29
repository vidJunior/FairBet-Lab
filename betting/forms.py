from django import forms
from django.core.exceptions import ValidationError
from betting.models import Evento, Equipo


class CrearEventoForm(forms.ModelForm):
    local_nombre = forms.CharField(
        max_length=100,
        label="Equipo Local",
        widget=forms.TextInput(attrs={
            "placeholder": "Ej: Barcelona",
            "class": "w-full bg-white border-2 border-slate-200 focus:border-indigo-500 focus:ring-0 rounded-2xl py-3.5 px-4 text-base font-semibold text-slate-800 outline-none transition-all placeholder-slate-300 shadow-sm"
        })
    )
    visitante_nombre = forms.CharField(
        max_length=100,
        label="Equipo Visitante",
        widget=forms.TextInput(attrs={
            "placeholder": "Ej: Real Madrid",
            "class": "w-full bg-white border-2 border-slate-200 focus:border-indigo-500 focus:ring-0 rounded-2xl py-3.5 px-4 text-base font-semibold text-slate-800 outline-none transition-all placeholder-slate-300 shadow-sm"
        })
    )

    class Meta:
        model = Evento
        fields = ["local_nombre", "visitante_nombre", "fecha_inicio"]
        widgets = {
            "fecha_inicio": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "w-full bg-white border-2 border-slate-200 focus:border-indigo-500 focus:ring-0 rounded-2xl py-3.5 px-4 text-base font-semibold text-slate-800 outline-none transition-all shadow-sm",
            }, format="%Y-%m-%dT%H:%M"),
        }
        labels = {
            "fecha_inicio": "Fecha y Hora del Evento",
        }

    def clean_local_nombre(self):
        nombre = self.cleaned_data["local_nombre"].strip()
        if not nombre:
            raise ValidationError("El nombre del equipo local no puede estar vacío.")
        return nombre

    def clean_visitante_nombre(self):
        nombre = self.cleaned_data["visitante_nombre"].strip()
        if not nombre:
            raise ValidationError("El nombre del equipo visitante no puede estar vacío.")
        return nombre

    def clean(self):
        cleaned_data = super().clean()
        local = cleaned_data.get("local_nombre")
        visitante = cleaned_data.get("visitante_nombre")

        if local and visitante and local.lower() == visitante.lower():
            raise ValidationError("El equipo local y visitante no pueden ser el mismo.")

        return cleaned_data

    def save(self, commit=True):
        local_nombre = self.cleaned_data["local_nombre"]
        visitante_nombre = self.cleaned_data["visitante_nombre"]

        local_equipo, _ = Equipo.objects.get_or_create(nombre__iexact=local_nombre, defaults={"nombre": local_nombre})
        visitante_equipo, _ = Equipo.objects.get_or_create(nombre__iexact=visitante_nombre, defaults={"nombre": visitante_nombre})

        if local_equipo.nombre.lower() != local_nombre.lower():
            local_nombre = local_equipo.nombre
        if visitante_equipo.nombre.lower() != visitante_nombre.lower():
            visitante_nombre = visitante_equipo.nombre

        self.instance.local = local_nombre
        self.instance.visitante = visitante_nombre
        self.instance.local_equipo = local_equipo
        self.instance.visitante_equipo = visitante_equipo

        return super().save(commit=commit)
