from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse, Http404
from django.db.models import Q, Count
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from functools import wraps
from datetime import timedelta
from decimal import Decimal
import uuid
import os

from django.utils import timezone

from .models import (
    Song, Artist, Album, Genre, Playlist, Purchase,
    PlayHistory, Follow, Notification, SongComment, UserProfile,
    PremiumSubscription, ArtistWallet, WalletTransaction,
    WithdrawalRequest, PaymentLog,
)
from .forms import SongForm, ArtistForm, PlaylistForm
from .utils import (
    user_has_premium, get_purchased_ids, get_or_create_wallet,
    credit_play_royalty, credit_sale_royalty,
)



def is_artist(user):
    """Return True if the authenticated user has an Artist profile."""
    return hasattr(user, 'artist')


def user_has_premium(user):
    """Return True if the user has an active premium subscription."""
    if not user.is_authenticated:
        return False
    try:
        
        return user.subscription.is_active()
    except PremiumSubscription.DoesNotExist:
        return False


def artist_required(view_func):
    """Decorator: user must have an Artist profile."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_artist(request.user):
            messages.warning(
                request,
                
                '🎤 Only artists can do that. Become an artist to upload music and earn!'
            )
            return redirect('music:become_artist')
        return view_func(request, *args, **kwargs)
    return wrapper


def artist_mode_required(view_func):
    """Decorator: user must have Artist profile AND be in Artist Mode."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_artist(request.user):
            messages.warning(
                request,
                '🎤 You need an artist profile first. Create one to start uploading music!'
            )
            return redirect('music:become_artist')
        if request.session.get('mode') != 'artist':
            request.session['mode'] = 'artist'
            messages.info(request, '🎙 Automatically switched to Artist Mode.')
        return view_func(request, *args, **kwargs)
    return wrapper


def get_or_create_wallet(artist):
    """Get or create an ArtistWallet for the given Artist."""
    wallet, _ = ArtistWallet.objects.get_or_create(artist=artist)
    return wallet



def landing(request):
    if request.user.is_authenticated:
        return redirect('music:home')
    return render(request, 'landing.html')


def logged_out_page(request):
    return render(request, 'logged_out.html')


@login_required
def switch_mode(request):
    """Toggle between Artist and Listener modes."""
    if not is_artist(request.user):
        messages.info(request, '🎤 Create an artist profile to unlock Artist Mode!')
        return redirect('music:become_artist')

    current = request.session.get('mode', 'listener')
    if current == 'listener':
        request.session['mode'] = 'artist'
        messages.success(
            request,
            '🎙 Switched to Artist Mode — you can now upload and manage your music.'
        )
        return redirect('music:artist_panel')
    else:
        request.session['mode'] = 'listener'
        messages.success(request, '🎧 Switched to Listener Mode — enjoy the music!')
        return redirect('music:home')





@login_required
def home(request):
    query = request.GET.get('q', '')
    songs = Song.objects.select_related('artist', 'album').prefetch_related('genres')
    if query:
        songs = songs.filter(
            Q(title__icontains=query) | Q(artist__name__icontains=query)
        )
    is_premium = user_has_premium(request.user)
    # Build a set of song IDs the user has purchased (for quick template checks)
    purchased_ids = get_purchased_ids(request.user)
    return render(request, 'home.html', {
        'songs': songs,
        'query': query,
        'is_premium': is_premium,
        'purchased_ids': purchased_ids,
    })


def song_list(request):
    query = request.GET.get('q', '')
    songs = Song.objects.select_related('artist', 'album').all()
    if query:
        songs = songs.filter(
            Q(title__icontains=query) | Q(artist__name__icontains=query)
            
        )
    is_premium = user_has_premium(request.user) if request.user.is_authenticated else False
    purchased_ids = get_purchased_ids(request.user)
    return render(request, 'song_list.html', {
        'songs': songs,
        'query': query,
        'is_premium': is_premium,
        'purchased_ids': purchased_ids,
    })



def song_detail(request, pk):
    song = get_object_or_404(Song, pk=pk)
    is_premium_user = user_has_premium(request.user) if request.user.is_authenticated else False
    purchased = song.is_purchased_by(request.user) if request.user.is_authenticated else False




    
    can_play = song.can_play(request.user) if request.user.is_authenticated else (not song.is_premium)
    can_download = purchased  
    

    comments = song.comments.select_related('user').all()[:50]
    return render(request, 'detail.html', {
        'song': song,
        'purchased': purchased,
        'can_play': can_play,
        'can_download': can_download,
        'is_premium_user': is_premium_user,
        'comments': comments,
    })


@login_required
@require_POST
def record_play(request, pk):
    """AJAX endpoint — called when the audio player actually starts playing.
    Blocked if the user does not have access to a premium song."""
    song = get_object_or_404(Song, pk=pk)


    
    if not song.can_play(request.user):
        return JsonResponse(
            {'ok': False, 'error': 'premium_required', 'song_id': pk},
            status=403
        )

    song.play_count += 1
    song.save(update_fields=['play_count'])
    PlayHistory.objects.create(user=request.user, song=song)
    credit_play_royalty(song)
    return JsonResponse({'ok': True})






@login_required
def download_song(request, pk):
    """Serve the audio file as an attachment — only for buyers."""
    song = get_object_or_404(Song, pk=pk)

    if not song.can_download(request.user):
        messages.error(
            request,
            '🔒 You need to purchase this song before you can download it.'
        )
        return redirect('music:song_detail', pk=pk)

    file_path = song.audio_file.path
    if not os.path.exists(file_path):
        raise Http404("Audio file not found on server.")

    ext = os.path.splitext(file_path)[1]
    filename = f"{song.title}{ext}".replace(' ', '_')
    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
    return response






@artist_mode_required
def create_song(request):
    if request.method == 'POST':
        form = SongForm(request.POST, request.FILES, artist=request.user.artist)
        if form.is_valid():
            song = form.save(commit=False)
            song.artist = request.user.artist
            song.save()
            form.save_m2m()
            artist = request.user.artist
            for follow in artist.followers.select_related('follower'):
                Notification.objects.create(
                    user=follow.follower,
                    message=f'🎵 {artist.name} just uploaded "{song.title}"!',
                    link=f'/music/songs/{song.pk}/',
                )
            messages.success(request, f'"{song.title}" uploaded successfully!')
            return redirect('music:artist_panel')
    else:
        form = SongForm(artist=request.user.artist)
    return render(request, 'form.html', {'form': form, 'action': 'Upload Song'})


@artist_mode_required
def update_song(request, pk):
    song = get_object_or_404(Song, pk=pk, artist=request.user.artist)
    if request.method == 'POST':
        form = SongForm(request.POST, request.FILES, instance=song, artist=request.user.artist)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{song.title}" updated!')
            return redirect('music:artist_panel')
    else:
        form = SongForm(instance=song, artist=request.user.artist)
    return render(request, 'form.html', {'form': form, 'action': 'Edit Song', 'song': song})


@artist_mode_required
def delete_song(request, pk):
    song = get_object_or_404(Song, pk=pk, artist=request.user.artist)
    if request.method == 'POST':
        title = song.title
        song.delete()
        messages.success(request, f'"{title}" deleted.')
        return redirect('music:artist_panel')
    return render(request, 'confirm_delete.html', {'song': song})


@login_required
def like_song(request, pk):
    song = get_object_or_404(Song, pk=pk)
    if request.user in song.likes.all():
        song.likes.remove(request.user)
        liked = False
    else:
        song.likes.add(request.user)
        liked = True
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'liked': liked, 'count': song.likes.count()})
    return redirect(request.META.get('HTTP_REFERER', 'music:home'))




@login_required
def my_playlists(request):
    playlists = Playlist.objects.filter(user=request.user).prefetch_related('songs')
    form = PlaylistForm()
    if request.method == 'POST':
        form = PlaylistForm(request.POST)
        if form.is_valid():
            pl = form.save(commit=False)
            pl.user = request.user
            pl.save()
            messages.success(request, f'Playlist "{pl.name}" created!')
            return redirect('music:playlists')
    return render(request, 'playlists.html', {'playlists': playlists, 'form': form})


@login_required
def playlist_detail(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk, user=request.user)
    return render(request, 'playlist.html', {'playlist': playlist})


@login_required
def delete_playlist(request, pk):
    playlist = get_object_or_404(Playlist, pk=pk, user=request.user)
    if request.method == 'POST':
        name = playlist.name
        playlist.delete()
        messages.success(request, f'Playlist "{name}" deleted.')
    return redirect('music:playlists')


@login_required
def add_to_playlist(request, song_id):
    song = get_object_or_404(Song, id=song_id)
    if request.method == 'POST':
        playlist_id = request.POST.get('playlist_id')
        new_name = request.POST.get('new_playlist_name', '').strip()
        if playlist_id:
            target = get_object_or_404(Playlist, pk=playlist_id, user=request.user)
        elif new_name:
            target = Playlist.objects.create(user=request.user, name=new_name)
        else:
            target, _ = Playlist.objects.get_or_create(
                user=request.user, is_default=True,
                defaults={'name': 'My Playlist'}
            )
        target.songs.add(song)
        messages.success(request, f'Added "{song.title}" to "{target.name}"!')
        return redirect('music:song_detail', pk=song.pk)
    playlists = Playlist.objects.filter(user=request.user)
    return render(request, 'add_to_playlist.html', {'song': song, 'playlists': playlists})


@login_required
def remove_from_playlist(request, playlist_id, song_id):
    playlist = get_object_or_404(Playlist, pk=playlist_id, user=request.user)
    song = get_object_or_404(Song, pk=song_id)
    playlist.songs.remove(song)
    messages.success(request, f'Removed "{song.title}" from "{playlist.name}".')
    return redirect('music:playlist_detail', pk=playlist_id)





@login_required
def play_history(request):
    seen = set()
    history = []
    for entry in PlayHistory.objects.filter(user=request.user).select_related('song__artist')[:200]:
        if entry.song_id not in seen:
            seen.add(entry.song_id)
            history.append(entry)
        if len(history) >= 50:
            break
    return render(request, 'history.html', {'history': history})






@login_required
def user_profile(request, username=None):
    from django.contrib.auth.models import User as AuthUser
    if username:
        profile_user = get_object_or_404(AuthUser, username=username)
    else:
        profile_user = request.user

    user_profile_obj, _ = UserProfile.objects.get_or_create(user=profile_user)
    liked_songs = profile_user.liked_songs.select_related('artist').all()[:20]
    playlists = Playlist.objects.filter(user=profile_user)
    following = Follow.objects.filter(follower=profile_user).select_related('artist')[:20]

    subscription = None
    try:
        subscription = profile_user.subscription
    except PremiumSubscription.DoesNotExist:
        pass



    
    purchased_songs = []
    if profile_user == request.user:
        purchased_songs = list(
            Purchase.objects.filter(user=profile_user, status='completed')
            .select_related('song__artist')
            .order_by('-paid_at')[:20]
        )

    recent_plays = []
    if profile_user == request.user:
        seen = set()
        for entry in PlayHistory.objects.filter(user=profile_user).select_related('song__artist')[:100]:
            if entry.song_id not in seen:
                seen.add(entry.song_id)
                recent_plays.append(entry.song)
            if len(recent_plays) >= 6:
                break

    return render(request, 'profile.html', {
        'profile_user': profile_user,
        'profile': user_profile_obj,
        'user_profile': user_profile_obj,
        'liked_songs': liked_songs,
        'playlists': playlists,
        'following': following,
        'followed_artists': [f.artist for f in following],
        'recent_plays': recent_plays,
        'purchased_songs': purchased_songs,
        'recent_history': (
            PlayHistory.objects.filter(user=profile_user).select_related('song__artist')[:8]
            if profile_user == request.user else []
        ),
        'is_own': profile_user == request.user,
        'subscription': subscription,
    })




@login_required
def follow_artist(request, artist_id):
    artist = get_object_or_404(Artist, pk=artist_id)
    follow, created = Follow.objects.get_or_create(follower=request.user, artist=artist)
    if created:
        following = True
        Notification.objects.create(
            user=request.user,
            message=f'You are now following {artist.name}!',
            link=f'/music/artist/{artist.pk}/page/',
        )
    else:
        follow.delete()
        following = False
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'following': following, 'count': artist.follower_count()})
    return redirect(request.META.get('HTTP_REFERER', 'music:home'))





@login_required
def notifications(request):
    notifs = Notification.objects.filter(user=request.user)
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'notifications.html', {'notifs': notifs})


@login_required
def unread_notification_count(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'count': count})




def artist_page(request, artist_id):
    artist = get_object_or_404(Artist, pk=artist_id)
    songs = Song.objects.filter(artist=artist).order_by('-created_at')
    is_following = False
    purchased_ids = set()
    is_premium = False
    if request.user.is_authenticated:
        is_following = Follow.objects.filter(follower=request.user, artist=artist).exists()
        purchased_ids = set(
            Purchase.objects.filter(user=request.user, status='completed')
            .values_list('song_id', flat=True)
        )
        is_premium = user_has_premium(request.user)
    return render(request, 'artist_page.html', {
        'artist': artist,
        'songs': songs,
        'is_following': is_following,
        'follower_count': artist.follower_count(),
        'purchased_ids': purchased_ids,
        'is_premium': is_premium,
    })





def search_songs(request):
    """JSON API for live/instant search at /music/api/search/."""
    query = request.GET.get('q', '')
    songs = Song.objects.select_related('artist').filter(
        Q(title__icontains=query) | Q(artist__name__icontains=query)
    )[:20]
    data = [{
        'id': s.id,
        'title': s.title,
        'artist': s.artist.name if s.artist else 'Unknown',
        'audio': s.audio_file.url,
        'cover': s.cover_image.url if s.cover_image else '',
        'is_premium': s.is_premium,
        'price': str(s.price),
    } for s in songs]
    return JsonResponse({'songs': data})


def global_search(request):
    """Full search results page at /music/search/."""
    query = request.GET.get('q', '').strip()
    songs, artists, genres = [], [], []
    if query:
        songs = Song.objects.filter(
            Q(title__icontains=query) | Q(artist__name__icontains=query)
        ).select_related('artist')[:12]
        artists = Artist.objects.filter(name__icontains=query)[:6]
        genres = Genre.objects.filter(name__icontains=query)[:6]
    is_premium = user_has_premium(request.user) if request.user.is_authenticated else False
    purchased_ids = set(
        Purchase.objects.filter(user=request.user, status='completed')
        .values_list('song_id', flat=True)
    ) if request.user.is_authenticated else set()
    return render(request, 'search_results.html', {
        'query': query,
        'songs': songs,
        'artists': artists,
        'genres': genres,
        'all_genres': Genre.objects.all()[:20],
        'is_premium': is_premium,
        'purchased_ids': purchased_ids,
    })






@artist_required
def artist_panel(request):
    artist = request.user.artist
    songs = Song.objects.filter(artist=artist).prefetch_related('likes', 'purchases')
    total_plays = sum(s.play_count for s in songs)
    total_likes = sum(s.likes.count() for s in songs)
    earnings_qs = Purchase.objects.filter(song__artist=artist, status='completed')
    total_earned = sum(p.amount for p in earnings_qs)
    total_sales = earnings_qs.count()
    premium_songs = [s for s in songs if s.is_premium]
    stream_earnings = (total_plays / 1000) * 0.50
    estimated_earnings = stream_earnings + float(total_earned)

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_plays = PlayHistory.objects.filter(
        song__artist=artist, played_at__gte=month_start
    ).count()
    monthly_stream_earn = (monthly_plays / 1000) * 0.50

    return render(request, 'artist_panel.html', {
        'artist': artist,
        'songs': songs,
        'total_plays': total_plays,
        'total_likes': total_likes,
        'total_earned': total_earned,
        'total_sales': total_sales,
        'premium_songs': premium_songs,
        'stream_earnings': stream_earnings,
        'estimated_earnings': estimated_earnings,
        'monthly_plays': monthly_plays,
        'monthly_stream_earn': monthly_stream_earn,
        'follower_count': artist.follower_count(),
    })


@login_required
def become_artist(request):
    if is_artist(request.user):
        return redirect('music:artist_panel')
    if request.method == 'POST':
        form = ArtistForm(request.POST, request.FILES)
        if form.is_valid():
            artist = form.save(commit=False)
            artist.user = request.user
            artist.save()
            get_or_create_wallet(artist)
            request.session['mode'] = 'artist'
            messages.success(request, 'Artist profile created! You can now upload songs.')
            return redirect('music:artist_panel')
    else:
        form = ArtistForm()
    return render(request, 'become_artist.html', {'form': form})





@login_required
def add_comment(request, song_id):
    song = get_object_or_404(Song, pk=song_id)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            comment = SongComment.objects.create(user=request.user, song=song, text=text[:500])
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'ok': True,
                    'username': request.user.username,
                    'text': comment.text,
                    'time': 'just now',
                    'id': comment.id,
                })
    return redirect('music:song_detail', pk=song_id)


@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(SongComment, pk=comment_id)
    if comment.user == request.user or request.user.is_superuser:
        song_pk = comment.song_id
        comment.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect('music:song_detail', pk=song_pk)
    return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)





@login_required
def edit_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        bio = request.POST.get('bio', '').strip()[:300]
        color = request.POST.get('avatar_color', '#1DB954')
        profile.bio = bio
        profile.avatar_color = color
        profile.save()
        email = request.POST.get('email', '').strip()
        if email:
            request.user.email = email
            request.user.save(update_fields=['email'])
        messages.success(request, 'Profile updated!')
        return redirect('music:my_profile')
    return render(request, 'edit_profile.html', {'profile': profile})





@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password1 = request.POST.get('new_password1', '')
        new_password2 = request.POST.get('new_password2', '')

        if not request.user.check_password(old_password):
            messages.error(request, 'Current password is incorrect.')
        elif len(new_password1) < 8:
            messages.error(request, 'New password must be at least 8 characters.')
        elif new_password1 != new_password2:
            messages.error(request, 'New passwords do not match.')
        else:
            request.user.set_password(new_password1)
            request.user.save()
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully!')
            return redirect('music:my_profile')
    return render(request, 'change_password.html')





def top_charts(request):
    top_songs = Song.objects.order_by('-play_count')[:20]
    top_liked = Song.objects.annotate(like_count=Count('likes')).order_by('-like_count')[:10]
    genres = Genre.objects.all()
    genre_id = request.GET.get('genre')
    if genre_id:
        top_songs = top_songs.filter(genres__id=genre_id)
    return render(request, 'charts.html', {
        'top_songs': top_songs,
        'top_liked': top_liked,
        'genres': genres,
        'selected_genre': int(genre_id) if genre_id else None,
    })




def browse_genres(request):
    genres = Genre.objects.annotate(song_count=Count('song')).all()
    return render(request, 'genres.html', {'genres': genres})


def genre_songs(request, genre_id):
    genre = get_object_or_404(Genre, pk=genre_id)
    songs = Song.objects.filter(genres=genre).select_related('artist')
    is_premium = user_has_premium(request.user) if request.user.is_authenticated else False
    purchased_ids = set(
        Purchase.objects.filter(user=request.user, status='completed')
        .values_list('song_id', flat=True)
    ) if request.user.is_authenticated else set()
    return render(request, 'genre_songs.html', {
        'genre': genre,
        'songs': songs,
        'is_premium': is_premium,
        'purchased_ids': purchased_ids,
    })




def all_artists(request):
    query = request.GET.get('q', '')
    artists = Artist.objects.annotate(song_count=Count('songs')).all()
    if query:
        artists = artists.filter(name__icontains=query)
    return render(request, 'all_artists.html', {'artists': artists, 'query': query})


# ── QUEUE (AJAX) ──────────────────────────────────────────────────────────────

@login_required
def get_queue(request):
    seen = set()
    queue = []
    for entry in PlayHistory.objects.filter(user=request.user).select_related('song__artist')[:100]:
        if entry.song_id not in seen:
            seen.add(entry.song_id)
            s = entry.song
            queue.append({
                'id': s.id,
                'title': s.title,
                'artist': s.artist.name if s.artist else '',
                'audio': s.audio_file.url,
                'cover': s.cover_image.url if s.cover_image else '',
            })
        if len(queue) >= 10:
            break
    return JsonResponse({'queue': queue})


# ── PREMIUM SUBSCRIPTION ──────────────────────────────────────────────────────

PLAN_META = {
    'individual': {
        'name': 'Individual',
        'price': 199,
        'color': '#1DB954',
        'icon': '🎧',
        'popular': True,
        'features': [
            'Stream ALL premium songs ad-free',
            'High-quality audio (320kbps)',
            'Unlimited skips',
            'Offline playback (coming soon)',
            'Exclusive artist content',
        ],
    },
    'student': {
        'name': 'Student',
        'price': 99,
        'color': '#3D91F4',
        'icon': '🎓',
        'popular': False,
        'features': [
            'Stream ALL premium songs ad-free',
            'High-quality audio (320kbps)',
            'Unlimited skips',
            'Valid student ID required',
        ],
    },
    'family': {
        'name': 'Family',
        'price': 349,
        'color': '#F4A93D',
        'icon': '👨‍👩‍👧‍👦',
        'popular': False,
        'features': [
            'Up to 6 accounts',
            'Stream ALL premium songs ad-free',
            'High-quality audio (320kbps)',
            'Unlimited skips',
            'Family mix playlist',
        ],
    },
}


@login_required
def subscription_plans(request):
    subscription = None
    try:
        subscription = request.user.subscription
    except PremiumSubscription.DoesNotExist:
        pass
    return render(request, 'subscription.html', {
        'plans': PLAN_META,
        'subscription': subscription,
    })


@login_required
def subscribe(request, plan):
    if plan not in PLAN_META:
        messages.error(request, 'Invalid plan selected.')
        return redirect('music:subscription_plans')

    try:
        existing = request.user.subscription
        if existing.is_active():
            messages.info(
                request,
                f'You already have an active {existing.get_plan_display()} subscription.'
            )
            return redirect('music:subscription_dashboard')
    except PremiumSubscription.DoesNotExist:
        pass

    price = PLAN_META[plan]['price']
    tran_id = f"GH-SUB-{request.user.id}-{uuid.uuid4().hex[:8].upper()}"

    # Created as NOT active. Premium only starts after payment is submitted.
    subscription, _ = PremiumSubscription.objects.update_or_create(
        user=request.user,
        defaults={
            'plan': plan,
            'status': 'expired',
            'expires_at': timezone.now(),
            'transaction_id': tran_id,
            'amount_paid': price,
        }
    )
    return redirect('music:payment_gateway_select', purpose='subscription', ref_id=subscription.id)


@login_required
def subscription_success(request, subscription_id):
    from django.db import transaction as db_transaction
    # DEMO: no gateway verification. Only the owner can activate, and only once.
    with db_transaction.atomic():
        subscription = get_object_or_404(
            PremiumSubscription.objects.select_for_update(),
            id=subscription_id, user=request.user,
        )
        if subscription.is_active():
            messages.info(request, 'Your subscription is already active.')
            return redirect('music:subscription_dashboard')
        subscription.status = 'active'
        subscription.expires_at = timezone.now() + timedelta(days=30)
        subscription.save()
    Notification.objects.create(
        user=subscription.user,
        message=f'🎉 Welcome to GaanHub Premium ({subscription.get_plan_display()})! Enjoy ad-free music.',
        link='/music/subscription/dashboard/',
    )
    messages.success(
        request,
        f'🎉 Welcome to GaanHub Premium! Your {subscription.get_plan_display()} plan is now active.'
    )
    return redirect('music:subscription_dashboard')


@csrf_exempt
def subscription_fail(request):
    messages.error(request, 'Subscription payment failed. Please try again.')
    return redirect('music:subscription_plans')


@csrf_exempt
def subscription_cancel_payment(request):
    messages.warning(request, 'Subscription payment cancelled.')
    return redirect('music:subscription_plans')


@login_required
def subscription_dashboard(request):
    subscription = None
    try:
        subscription = request.user.subscription
    except PremiumSubscription.DoesNotExist:
        pass
    plan_meta = PLAN_META.get(subscription.plan, {}) if subscription else {}
    return render(request, 'subscription_dashboard.html', {
        'subscription': subscription,
        'plan_meta': plan_meta,
    })


@login_required
def cancel_subscription(request):
    if request.method == 'POST':
        try:
            sub = request.user.subscription
            sub.status = 'cancelled'
            sub.auto_renew = False
            sub.save()
            messages.success(
                request,
                'Your subscription has been cancelled. Premium benefits continue until expiry.'
            )
        except PremiumSubscription.DoesNotExist:
            messages.error(request, 'No active subscription found.')
    return redirect('music:subscription_dashboard')


# ── PAYMENT (Song Purchase) ───────────────────────────────────────────────────

@login_required
def buy_song(request, pk):
    song = get_object_or_404(Song, pk=pk)
    if not song.is_premium:
        messages.info(request, 'This song is free!')
        return redirect('music:song_detail', pk=pk)
    if song.is_purchased_by(request.user):
        messages.info(request, 'You already own this song.')
        return redirect('music:song_detail', pk=pk)
    tran_id = f"GH-{request.user.id}-{song.id}-{uuid.uuid4().hex[:8].upper()}"
    purchase, _ = Purchase.objects.get_or_create(
        user=request.user, song=song,
        defaults={'amount': song.price, 'transaction_id': tran_id, 'status': 'pending'}
    )
    return redirect('music:payment_gateway_select', purpose='song', ref_id=purchase.id)


@login_required
def payment_success(request, purchase_id):
    from django.db import transaction as db_transaction
    # DEMO: no gateway verification. Only the buyer can complete, and only once.
    with db_transaction.atomic():
        purchase = get_object_or_404(
            Purchase.objects.select_for_update(),
            id=purchase_id, user=request.user,
        )
        if purchase.status == 'completed':
            messages.info(request, 'This purchase is already completed.')
            return redirect('music:song_detail', pk=purchase.song.pk)
        purchase.status = 'completed'
        purchase.save()
        credit_sale_royalty(purchase.song, purchase.amount)
    _notify_purchase_complete(request, purchase)
    messages.success(request, f'✅ Payment confirmed! Enjoy "{purchase.song.title}".')
    return redirect('music:song_detail', pk=purchase.song.pk)


@csrf_exempt
def payment_fail(request):
    messages.error(request, 'Payment failed. Please try again.')
    return redirect('music:home')


@csrf_exempt
def payment_cancel(request):
    messages.warning(request, 'Payment cancelled.')
    return redirect('music:home')


def _notify_purchase_complete(request, purchase):
    """Send a notification to the buyer confirming their purchase."""
    Notification.objects.create(
        user=purchase.user,
        message=(
            f'✅ You purchased "{purchase.song.title}"! '
            f'You can now stream and download it anytime.'
        ),
        link=f'/music/songs/{purchase.song.pk}/',
    )


# ── WALLET & EARNINGS ─────────────────────────────────────────────────────────

@login_required
def wallet_dashboard(request):
    if not is_artist(request.user):
        messages.warning(request, '🎤 Only artists have a wallet. Become an artist first!')
        return redirect('music:become_artist')
    artist = request.user.artist
    wallet = get_or_create_wallet(artist)
    transactions = wallet.transactions.all()[:30]
    withdrawals = wallet.withdrawals.all()[:10]
    songs = Song.objects.filter(artist=artist)
    total_plays = sum(s.play_count for s in songs)
    stream_earnings = Decimal(str(round((total_plays / 1000) * 0.50, 2)))
    sales_earnings = sum(
        p.amount for p in Purchase.objects.filter(song__artist=artist, status='completed')
    )
    return render(request, 'wallet_dashboard.html', {
        'wallet': wallet,
        'transactions': transactions,
        'withdrawals': withdrawals,
        'stream_earnings': stream_earnings,
        'sales_earnings': sales_earnings,
        'total_plays': total_plays,
    })


@login_required
def request_withdrawal(request):
    from django.db import transaction as db_transaction
    if not is_artist(request.user):
        return redirect('music:become_artist')
    artist = request.user.artist
    wallet = get_or_create_wallet(artist)
    MIN_WITHDRAWAL = Decimal('100.00')
    VALID_METHODS = {'bkash', 'nagad', 'rocket', 'bank'}

    if request.method == 'POST':
        method = request.POST.get('method', '').strip()
        if method not in VALID_METHODS:
            messages.error(request, 'Please choose a valid withdrawal method.')
            return redirect('music:request_withdrawal')
        try:
            amount = Decimal(request.POST.get('amount', '0')).quantize(Decimal('0.01'))
            if not amount.is_finite():
                raise ValueError
        except Exception:
            messages.error(request, 'Invalid amount.')
            return redirect('music:request_withdrawal')

        if amount < MIN_WITHDRAWAL:
            messages.error(request, f'Minimum withdrawal is ৳{MIN_WITHDRAWAL}.')
            return redirect('music:request_withdrawal')

        wr = WithdrawalRequest(wallet=wallet, amount=amount, method=method)

        if method in ('bkash', 'nagad', 'rocket'):
            wr.mobile_number = request.POST.get('mobile_number', '').strip()
            wr.account_name = request.POST.get('account_name', '').strip()
            if not wr.mobile_number:
                messages.error(request, 'Mobile number is required.')
                return redirect('music:request_withdrawal')
        elif method == 'bank':
            wr.bank_name = request.POST.get('bank_name', '').strip()
            wr.branch_name = request.POST.get('branch_name', '').strip()
            wr.account_number = request.POST.get('account_number', '').strip()
            wr.routing_number = request.POST.get('routing_number', '').strip()
            wr.account_name = request.POST.get('account_name', '').strip()
            if not wr.account_number:
                messages.error(request, 'Account number is required.')
                return redirect('music:request_withdrawal')

        wr.note = request.POST.get('note', '').strip()

        # Save the request and take the money in ONE transaction.
        # debit() locks the wallet row and re-checks the balance.
        try:
            with db_transaction.atomic():
                wr.save()
                wallet.debit(amount, description=f'Withdrawal via {wr.get_method_display()} — #{wr.id}')
        except ValueError:
            wallet.refresh_from_db()
            messages.error(request, f'Insufficient balance. Your balance is ৳{wallet.balance}.')
            return redirect('music:request_withdrawal')

        Notification.objects.create(
            user=request.user,
            message=(
                f"💸 Withdrawal request of ৳{amount} via {wr.get_method_display()} submitted."
                f" We'll process it within 3 business days."
            ),
            link='/music/wallet/',
        )
        messages.success(
            request,
            f'✅ Withdrawal request of ৳{amount} submitted! Processing within 3 business days.'
        )
        return redirect('music:wallet_dashboard')

    return render(request, 'withdrawal_request.html', {
        'wallet': wallet,
        'MIN_WITHDRAWAL': MIN_WITHDRAWAL,
    })


# ── ROYALTY HELPERS are in music/utils.py ────────────────────────────────────


# ── PAYMENT GATEWAY (bKash / Nagad / Rocket / Bank) ──────────────────────────

@login_required
def payment_gateway_select(request, purpose, ref_id):
    """Show gateway selection page for premium subscription or song purchase."""
    context = {'purpose': purpose, 'ref_id': ref_id}
    if purpose == 'subscription':
        sub = get_object_or_404(PremiumSubscription, id=ref_id, user=request.user)
        context['amount'] = sub.amount_paid
        context['description'] = f'GaanHub Premium — {sub.get_plan_display()}'
    elif purpose == 'song':
        purchase = get_object_or_404(Purchase, id=ref_id, user=request.user)
        context['amount'] = purchase.amount
        context['description'] = f'Song: {purchase.song.title}'
    else:
        return redirect('music:home')

    amount = context['amount']
    context['gateways'] = [
        ('bkash', 'bKash', '#E2136E', '💗', '01XXXXXXXXX', [
            'Open bKash app or dial *247#',
            'Tap "Payment" → "Merchant Payment"',
            'Enter merchant number: 01XXXXXXXXX',
            f'Enter amount: ৳{amount}',
            'Use your name or "GaanHub" as reference',
            'Complete payment and copy the TrxID from your SMS',
        ]),
        ('nagad', 'Nagad', '#F6A623', '🔶', '01XXXXXXXXX', [
            'Open Nagad app or dial *167#',
            'Tap "Make Payment"',
            'Enter merchant: 01XXXXXXXXX',
            f'Enter amount: ৳{amount} and complete',
            'Copy your Nagad Transaction ID from the confirmation',
        ]),
        ('rocket', 'Rocket', '#8B00FF', '🚀', '01XXXXXXXXX', [
            'Open Rocket app or dial *322#',
            'Choose "Payment"',
            'Enter merchant number: 01XXXXXXXXX',
            f'Pay ৳{amount} and confirm with your PIN',
            'Note the Transaction ID from your confirmation SMS',
        ]),
    ]
    context['bank_details'] = [
        ('Bank Name',      'Dutch-Bangla Bank Ltd (DBBL)', False),
        ('Account Name',   'GaanHub Entertainment Ltd',   False),
        ('Account Number', '1234567890123',                True),
        ('Branch',         'Mirpur, Dhaka',                False),
        ('Routing No.',    '090261234',                    True),
        ('Reference',      f'GH-{request.user.id}-{purpose[:3].upper()}', True),
    ]
    return render(request, 'payment_gateway_select.html', context)


@login_required
def payment_manual_submit(request, purpose, ref_id):
    import re
    from django.db import transaction as db_transaction
    # DEMO: the TrxID is recorded but NOT verified with bKash/Nagad/bank.
    if request.method != 'POST':
        return redirect('music:home')

    gateway = request.POST.get('gateway', '').strip().lower()
    trx_id = request.POST.get('trx_id', '').strip()
    back = redirect('music:payment_gateway_select', purpose=purpose, ref_id=ref_id)

    if gateway not in ('bkash', 'nagad', 'rocket', 'bank'):
        messages.error(request, 'Please choose a valid payment method.')
        return back
    if not re.fullmatch(r'[A-Za-z0-9_-]{6,60}', trx_id):
        messages.error(request, 'Please enter a valid Transaction ID (6-60 letters or digits).')
        return back
    if (Purchase.objects.filter(transaction_id=trx_id).exists()
            or PremiumSubscription.objects.filter(transaction_id=trx_id).exists()):
        messages.error(request, 'This Transaction ID has already been used.')
        return back

    log_trx = f"MANUAL-{gateway.upper()}-{uuid.uuid4().hex[:8].upper()}"

    if purpose == 'subscription':
        with db_transaction.atomic():
            sub = get_object_or_404(
                PremiumSubscription.objects.select_for_update(),
                id=ref_id, user=request.user,
            )
            if sub.is_active():
                messages.info(request, 'Your subscription is already active.')
                return redirect('music:subscription_dashboard')
            PaymentLog.objects.create(
                user=request.user, gateway=gateway,
                amount=sub.amount_paid,  # price comes from the server, never the form
                transaction_id=log_trx, purpose=purpose, status='unverified',
                raw_response=f'User submitted TrxID: {trx_id}',
            )
            sub.status = 'active'
            sub.transaction_id = trx_id
            sub.expires_at = timezone.now() + timedelta(days=30)
            sub.save()
        Notification.objects.create(
            user=request.user,
            message=f'🎉 Premium activated via {gateway}! Enjoy ad-free music.',
            link='/music/subscription/dashboard/',
        )
        messages.success(
            request,
            f'🎉 Premium activated! Your transaction ID {trx_id} has been recorded.'
        )
        return redirect('music:subscription_dashboard')

    elif purpose == 'song':
        with db_transaction.atomic():
            purchase = get_object_or_404(
                Purchase.objects.select_for_update(),
                id=ref_id, user=request.user,
            )
            if purchase.status == 'completed':
                messages.info(request, 'You already own this song.')
                return redirect('music:song_detail', pk=purchase.song.pk)
            PaymentLog.objects.create(
                user=request.user, gateway=gateway,
                amount=purchase.amount,  # price comes from the server, never the form
                transaction_id=log_trx, purpose=purpose, status='unverified',
                raw_response=f'User submitted TrxID: {trx_id}',
            )
            purchase.status = 'completed'
            purchase.transaction_id = trx_id
            purchase.save()
            # Artist royalty is credited exactly once, because the status check above
            # stops a second submission.
            credit_sale_royalty(purchase.song, purchase.amount)
        _notify_purchase_complete(request, purchase)
        messages.success(
            request,
            f'✅ Payment confirmed! You can now stream and download "{purchase.song.title}".'
        )
        return redirect('music:song_detail', pk=purchase.song.pk)

    return redirect('music:home')

