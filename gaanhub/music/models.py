from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Artist(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255, unique=True)
    bio = models.TextField(blank=True)
    image = models.ImageField(upload_to='artists/', blank=True, null=True)

    def __str__(self):
        return self.name

    def follower_count(self):
        return self.followers.count()


class Album(models.Model):
    title = models.CharField(max_length=255)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='albums')
    cover = models.ImageField(upload_to='albums/', blank=True, null=True)
    released_at = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.title} — {self.artist.name}"


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Song(models.Model):
    title = models.CharField(max_length=255)
    artist = models.ForeignKey(Artist, on_delete=models.SET_NULL, null=True, related_name='songs')
    album = models.ForeignKey(Album, on_delete=models.SET_NULL, null=True, blank=True, related_name='songs')
    genres = models.ManyToManyField(Genre, blank=True)
    audio_file = models.FileField(upload_to='songs/')
    cover_image = models.ImageField(upload_to='covers/', blank=True, null=True)

    is_premium = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    play_count = models.PositiveIntegerField(default=0)
    likes = models.ManyToManyField(User, related_name='liked_songs', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def is_purchased_by(self, user):
        """Return True if `user` has a completed purchase of this song."""
        if not user.is_authenticated:
            return False
        return Purchase.objects.filter(user=user, song=self, status='completed').exists()

    def user_has_premium(self, user):
        """Return True if `user` has an active premium subscription."""
        if not user.is_authenticated:
            return False
        try:
            return user.subscription.is_active()
        except PremiumSubscription.DoesNotExist:
            return False

    def can_play(self, user):
        """
        A user can play this song if:
          - The song is free (not premium), OR
          - The user has an active premium subscription, OR
          - The user has purchased this specific song.
        """
        if not self.is_premium:
            return True
        return self.user_has_premium(user) or self.is_purchased_by(user)

    def can_download(self, user):
        """
        Download is allowed only if the user has purchased this specific song.
        Premium subscribers can stream but need to buy to download.
        """
        if not user.is_authenticated:
            return False
        return self.is_purchased_by(user)


class Playlist(models.Model):
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playlists')
    songs = models.ManyToManyField(Song, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class Purchase(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchases')
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='purchases')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    transaction_id = models.CharField(max_length=200, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'song')

    def __str__(self):
        return f"{self.user.username} bought {self.song.title}"


class PlayHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='play_history')
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='history_entries')
    played_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-played_at']

    def __str__(self):
        return f"{self.user.username} played {self.song.title}"


class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'artist')

    def __str__(self):
        return f"{self.follower.username} follows {self.artist.name}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notif → {self.user.username}: {self.message[:40]}"


class SongComment(models.Model):
    song = models.ForeignKey(Song, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} on {self.song.title}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, max_length=300)
    avatar_color = models.CharField(max_length=7, default='#1DB954')

    def __str__(self):
        return f"Profile of {self.user.username}"



class PremiumSubscription(models.Model):
    PLAN_CHOICES = [
        ('individual', 'Individual'),
        ('student', 'Student'),
        ('family', 'Family'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    PLAN_PRICES = {
        'individual': 199,
        'student': 99,
        'family': 349,
    }

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    transaction_id = models.CharField(max_length=200, blank=True)
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    auto_renew = models.BooleanField(default=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user.username} — {self.get_plan_display()} ({self.status})"

    def is_active(self):
        return self.status == 'active' and self.expires_at > timezone.now()

    def days_remaining(self):
        if not self.is_active():
            return 0
        delta = self.expires_at - timezone.now()
        return max(0, delta.days)

    def plan_price(self):
        return self.PLAN_PRICES.get(self.plan, 0)


# ── ARTIST WALLET ─────────────────────────────────────────────────────────────

class ArtistWallet(models.Model):
    artist = models.OneToOneField(Artist, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_withdrawn = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet: {self.artist.name} — ৳{self.balance}"

    def credit(self, amount, description='', source='stream'):
        from decimal import Decimal
        from django.db import transaction
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be positive')
        with transaction.atomic():
            wallet = ArtistWallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance += amount
            wallet.total_earned += amount
            wallet.save(update_fields=['balance', 'total_earned', 'last_updated'])
            WalletTransaction.objects.create(
                wallet=wallet, amount=amount,
                transaction_type='credit', source=source,
                description=description,
            )
        self.refresh_from_db()

    def debit(self, amount, description=''):
        from decimal import Decimal
        from django.db import transaction
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be positive')
        with transaction.atomic():
            wallet = ArtistWallet.objects.select_for_update().get(pk=self.pk)
            if wallet.balance < amount:
                raise ValueError('Insufficient balance')
            wallet.balance -= amount
            wallet.total_withdrawn += amount
            wallet.save(update_fields=['balance', 'total_withdrawn', 'last_updated'])
            WalletTransaction.objects.create(
                wallet=wallet, amount=amount,
                transaction_type='debit', source='withdrawal',
                description=description,
            )
        self.refresh_from_db()


class WalletTransaction(models.Model):
    TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]
    SOURCE_CHOICES = [
        ('stream', 'Stream Royalty'),
        ('sale', 'Song Sale'),
        ('withdrawal', 'Withdrawal'),
        ('bonus', 'Bonus'),
    ]
    wallet = models.ForeignKey(ArtistWallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='stream')
    description = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} ৳{self.amount} — {self.wallet.artist.name}"


class WithdrawalRequest(models.Model):
    METHOD_CHOICES = [
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('rocket', 'Rocket'),
        ('bank', 'Bank Transfer'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    wallet = models.ForeignKey(ArtistWallet, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    mobile_number = models.CharField(max_length=15, blank=True)
    account_name = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    branch_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    routing_number = models.CharField(max_length=50, blank=True)
    note = models.TextField(blank=True)
    admin_note = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.wallet.artist.name} — ৳{self.amount} via {self.method} ({self.status})"


# ── PAYMENT GATEWAY LOG ───────────────────────────────────────────────────────

class PaymentLog(models.Model):
    GATEWAY_CHOICES = [
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('rocket', 'Rocket'),
        ('bank', 'Bank Transfer'),
        ('sslcommerz', 'SSLCommerz'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_logs')
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=200, unique=True)
    purpose = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='pending')
    raw_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} — {self.gateway} — ৳{self.amount} ({self.status})"
