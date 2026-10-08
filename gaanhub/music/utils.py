"""
music/utils.py — Shared utility functions for the music app.
Keeps views.py clean by extracting pure helper logic.
"""
from decimal import Decimal
from django.utils import timezone


def user_has_premium(user) -> bool:
    """Return True if the user has an active premium subscription."""
    if not user.is_authenticated:
        return False
    try:
        return user.subscription.is_active()
    except Exception:
        return False


def get_purchased_ids(user) -> set:
    """Return a set of song IDs the user has purchased (completed status)."""
    if not user.is_authenticated:
        return set()
    from .models import Purchase
    return set(
        Purchase.objects.filter(user=user, status='completed')
        .values_list('song_id', flat=True)
    )


def get_or_create_wallet(artist):
    """Get or create an ArtistWallet for the given Artist."""
    from .models import ArtistWallet
    wallet, _ = ArtistWallet.objects.get_or_create(artist=artist)
    return wallet


def credit_play_royalty(song) -> None:
    """Credit ৳0.50 per 1000 plays as a fractional royalty per play."""
    if not song.artist:
        return
    try:
        wallet = get_or_create_wallet(song.artist)
        royalty_per_play = Decimal('0.00050')  # ৳0.50 / 1000
        wallet.credit(royalty_per_play, description=f'Stream: {song.title}', source='stream')
    except Exception:
        pass  # Never crash a play because of wallet issues


def credit_sale_royalty(song, amount) -> None:
    """
    Credit 80% of sale price to the artist's wallet.
    The remaining 20% is GaanHub's platform fee.
    """
    if not song.artist:
        return
    try:
        from .models import Notification
        artist_share = Decimal(str(amount)) * Decimal('0.80')
        wallet = get_or_create_wallet(song.artist)
        wallet.credit(
            artist_share,
            description=f'Song sale: {song.title} (80% of ৳{amount})',
            source='sale',
        )
        if song.artist.user:
            Notification.objects.create(
                user=song.artist.user,
                message=f'💰 Someone bought "{song.title}"! ৳{artist_share:.2f} credited to your wallet.',
                link='/music/wallet/',
            )
    except Exception:
        pass
