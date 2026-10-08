"""
Management command: python manage.py seed_demo
Creates a demo superuser, artist, genre, and sample song entry for development.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from music.models import Artist, Genre, ArtistWallet, UserProfile


class Command(BaseCommand):
    help = 'Seed the database with demo data for development.'

    def handle(self, *args, **options):
        # Superuser
        if not User.objects.filter(username='admin').exists():
            admin = User.objects.create_superuser('admin', 'admin@gaanhub.local', 'admin1234')
            self.stdout.write(self.style.SUCCESS('Created superuser: admin / admin1234'))
        else:
            admin = User.objects.get(username='admin')
            self.stdout.write('Superuser "admin" already exists.')

        # UserProfile for admin
        UserProfile.objects.get_or_create(user=admin)

        # Demo Artist
        artist, created = Artist.objects.get_or_create(
            name='Demo Artist',
            defaults={'user': admin, 'bio': 'A demo artist created by seed_demo command.'}
        )
        ArtistWallet.objects.get_or_create(artist=artist)
        if created:
            self.stdout.write(self.style.SUCCESS('Created artist: Demo Artist'))
        else:
            self.stdout.write('Artist "Demo Artist" already exists.')

        # Genres
        genres = ['Pop', 'Rock', 'Hip-Hop', 'Jazz', 'Classical', 'Electronic', 'Folk', 'R&B']
        for name in genres:
            g, created = Genre.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f'  Created genre: {name}')

        self.stdout.write(self.style.SUCCESS('\n✅ Demo data seeded successfully!'))
        self.stdout.write('   Admin login: admin / admin1234')
        self.stdout.write('   Run: python manage.py runserver')
