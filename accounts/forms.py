from django import forms
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from config.choices import EstadoPerfil
from .models import PerfilUsuario, TipoAutoexclusion
from .validators import validar_dni, validar_mayor_edad


class LoginForm(forms.Form):
    """Formulario para iniciar sesión con validación de estados de cuenta"""

    username = forms.CharField(
        label="Usuario",
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "usuario123",
                "id": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "Tu contraseña",
                "id": "password",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        password = cleaned_data.get("password")

        if username and password:
            user = authenticate(username=username, password=password)
            if user is None:
                raise forms.ValidationError(
                    "Nombre de usuario o contraseña incorrectos."
                )

            perfil = getattr(user, "perfil", None)
            if perfil:
                if perfil.estado == EstadoPerfil.BLOQUEADO:
                    raise forms.ValidationError(
                        "Esta cuenta está bloqueada por el operador."
                    )
                elif (
                    perfil.estado == EstadoPerfil.AUTOEXCLUIDO
                    or perfil.esta_autoexcluido
                ):
                    if perfil.esta_autoexcluido:
                        if perfil.tipo_autoexclusion == TipoAutoexclusion.INDEFINIDA:
                            raise forms.ValidationError(
                                "Cuenta autoexcluida voluntariamente de forma indefinida."
                            )
                        elif perfil.fecha_autoexclusion_hasta:
                            fecha_str = perfil.fecha_autoexclusion_hasta.strftime(
                                "%d/%m/%Y %H:%M"
                            )
                            raise forms.ValidationError(
                                f"Cuenta autoexcluida voluntariamente hasta el {fecha_str}."
                            )
                    else:
                        # Autoexclusión expirada, se actualizará a verificado en la vista
                        pass
                elif perfil.estado == EstadoPerfil.PENDIENTE_VERIFICACION:
                    raise forms.ValidationError(
                        "La cuenta está pendiente de verificación."
                    )

            cleaned_data["user"] = user
        return cleaned_data


class RegistroForm(forms.Form):
    """Formulario para el registro de usuarios y KYC"""

    username = forms.CharField(
        label="Usuario",
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "usuario123",
                "id": "username",
            }
        ),
    )
    email = forms.EmailField(
        label="Correo Electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "correo@ejemplo.com",
                "id": "email",
            }
        ),
    )
    first_name = forms.CharField(
        label="Nombres",
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "Juan",
                "id": "first_name",
            }
        ),
    )
    last_name = forms.CharField(
        label="Apellidos",
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "Pérez",
                "id": "last_name",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "Mínimo 6 caracteres",
                "id": "password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirmar Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "Repite tu contraseña",
                "id": "password_confirm",
            }
        ),
    )
    fecha_nacimiento = forms.DateField(
        label="Fecha de Nacimiento",
        widget=forms.DateInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "type": "date",
                "id": "fecha_nacimiento",
            }
        ),
    )
    dni = forms.CharField(
        label="DNI (8 dígitos)",
        max_length=8,
        min_length=8,
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "12345678",
                "id": "dni",
                "maxlength": "8",
            }
        ),
    )
    digito_verificador = forms.CharField(
        label="Dígito Verificador",
        max_length=1,
        min_length=1,
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 bg-white",
                "placeholder": "0-9",
                "id": "digito_verificador",
                "maxlength": "1",
            }
        ),
    )

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya está en uso.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Este correo electrónico ya está registrado.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password and len(password) < 6:
            raise forms.ValidationError(
                "La contraseña debe tener al menos 6 caracteres."
            )
        return password

    def clean_fecha_nacimiento(self):
        fecha = self.cleaned_data.get("fecha_nacimiento")
        if fecha:
            # Capturar errores del validador y transformarlos a forms.ValidationError
            from django.core.exceptions import ValidationError as DjangoValidationError

            try:
                validar_mayor_edad(fecha)
            except DjangoValidationError as e:
                raise forms.ValidationError(e.messages)
        return fecha

    def clean_dni(self):
        dni = self.cleaned_data.get("dni")
        if dni:
            if not dni.isdigit():
                raise forms.ValidationError("El DNI debe contener solo números.")
            if PerfilUsuario.objects.filter(dni=dni).exists():
                raise forms.ValidationError("Este DNI ya está registrado.")

            # Validar DNI usando el validador
            from django.core.exceptions import ValidationError as DjangoValidationError

            try:
                validar_dni(dni)
            except DjangoValidationError as e:
                raise forms.ValidationError(e.messages)
        return dni

    def clean_digito_verificador(self):
        dv = self.cleaned_data.get("digito_verificador")
        if dv:
            if not dv.isdigit() or len(dv) != 1:
                raise forms.ValidationError("Debe ser un único dígito del 0 al 9.")
        return dv

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")

        # Validar DNI con digito verificador en conjunto
        dni = cleaned_data.get("dni")
        digito_verificador = cleaned_data.get("digito_verificador")
        if dni and digito_verificador:
            from django.core.exceptions import ValidationError as DjangoValidationError

            try:
                validar_dni(dni, digito_verificador)
            except DjangoValidationError as e:
                self.add_error("digito_verificador", e.messages)
        return cleaned_data


class LimitesDepositoForm(forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = [
            "limite_deposito_diario",
            "limite_deposito_semanal",
            "limite_deposito_mensual",
        ]
        widgets = {
            "limite_deposito_diario": forms.NumberInput(
                attrs={
                    "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 bg-white",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "limite_deposito_semanal": forms.NumberInput(
                attrs={
                    "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 bg-white",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "limite_deposito_mensual": forms.NumberInput(
                attrs={
                    "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 bg-white",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
        }


class AutoexclusionForm(forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = ["tipo_autoexclusion"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = []

        for c in TipoAutoexclusion.choices:
            if c[0] != TipoAutoexclusion.NINGUNA:
                opciones.append(c)

        self.fields["tipo_autoexclusion"].choices = opciones
        self.fields["tipo_autoexclusion"].widget.attrs.update(
            {
                "class": "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-slate-500 bg-white"
            }
        )
