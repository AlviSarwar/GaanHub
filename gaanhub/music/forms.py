from django import forms
from .models import Song, Artist, Album, Playlist


class SongForm(forms.ModelForm):
    class Meta:
        model = Song
        fields = ['title', 'album', 'genres', 'audio_file', 'cover_image', 'is_premium', 'price']
        widgets = {
            'genres': forms.CheckboxSelectMultiple(),
            'title': forms.TextInput(attrs={'placeholder': 'Song title'}),
            'price': forms.NumberInput(attrs={'placeholder': '0.00', 'min': '0', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        artist = kwargs.pop('artist', None)
        super().__init__(*args, **kwargs)
        if artist:
            self.fields['album'].queryset = Album.objects.filter(artist=artist)
        self.fields['album'].required = False
        self.fields['cover_image'].required = False
        # Only require audio_file on creation, not update
        if self.instance and self.instance.pk:
            self.fields['audio_file'].required = False

    def clean(self):
        cleaned = super().clean()
        is_premium = cleaned.get('is_premium')
        price = cleaned.get('price')
        if is_premium and (price is None or price <= 0):
            self.add_error('price', 'Premium songs must have a price greater than 0.')
        if not is_premium and price and price > 0:
            # Auto-reset price to 0 for free songs
            cleaned['price'] = 0
        return cleaned


class ArtistForm(forms.ModelForm):
    class Meta:
        model = Artist
        fields = ['name', 'bio', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Your artist name'}),
            'bio': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Tell us about yourself...'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Artist name is required.')
        # Check uniqueness (exclude current instance on updates)
        qs = Artist.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('An artist with this name already exists.')
        return name


class PlaylistForm(forms.ModelForm):
    class Meta:
        model = Playlist
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Playlist name...'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Playlist name is required.')
        return name
