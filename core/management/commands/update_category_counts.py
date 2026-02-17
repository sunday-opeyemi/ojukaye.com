# core/management/commands/update_category_counts.py
from django.core.management.base import BaseCommand
from core.models import Category, Post
from django.db.models import Count, Q

class Command(BaseCommand):
    help = 'Update cached post counts for all categories'
    
    def handle(self, *args, **options):
        categories = Category.objects.all()
        
        for category in categories:
            # Count published posts in this category
            count = Post.objects.filter(
                category=category,
                status='published'
            ).count()
            
            # Update the cached count
            category.cached_post_count = count
            category.save(update_fields=['cached_post_count'])
            
            self.stdout.write(f'Updated {category.name}: {count} posts')
        
        self.stdout.write(self.style.SUCCESS('Successfully updated all category counts'))