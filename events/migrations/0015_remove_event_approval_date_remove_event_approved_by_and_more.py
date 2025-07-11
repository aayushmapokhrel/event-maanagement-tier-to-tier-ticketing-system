# Generated by Django 5.0.2 on 2025-05-28 12:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0014_event_status_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='approval_date',
        ),
        migrations.RemoveField(
            model_name='event',
            name='approved_by',
        ),
        migrations.RemoveField(
            model_name='event',
            name='rejected_by',
        ),
        migrations.RemoveField(
            model_name='event',
            name='rejection_date',
        ),
        migrations.RemoveField(
            model_name='event',
            name='updated_at',
        ),
        migrations.AlterField(
            model_name='event',
            name='admin_notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='capacity',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='event',
            name='category',
            field=models.CharField(choices=[('MUSIC', 'Music'), ('EDUCATION', 'Education'), ('SPORTS', 'Sports'), ('COMMUNITY', 'Community'), ('OTHER', 'Other')], max_length=50),
        ),
        migrations.AlterField(
            model_name='event',
            name='custom_venue',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='event_images/'),
        ),
        migrations.AlterField(
            model_name='event',
            name='status',
            field=models.CharField(choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='PENDING', max_length=20),
        ),
    ]
