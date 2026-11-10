from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Service, GalleryItem, TimeSlot, Booking, Feedback

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'role', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role',)}),
    )

class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'booking', 'rating', 'is_visible', 'created_at')
    list_editable = ('is_visible',)
    list_filter = ('is_visible', 'rating', 'created_at')

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Service)
admin.site.register(GalleryItem)
admin.site.register(TimeSlot)
admin.site.register(Booking)
admin.site.register(Feedback, FeedbackAdmin)
