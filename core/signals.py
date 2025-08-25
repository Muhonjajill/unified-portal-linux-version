from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from core.models import ActivityLog, File, FileAccessLog, Profile, Ticket, TicketComment
from django.core.exceptions import ObjectDoesNotExist


@receiver(post_migrate)
def setup_groups_and_permissions(sender, **kwargs):
    """
    Signal that sets up user groups and file model permissions after migrations.
    """
    # File model permissions
    file_content_type = ContentType.objects.get_for_model(File)

    try:
        # File permissions for CRUD operations on files
        view_file = Permission.objects.get(codename='view_file')
        change_file = Permission.objects.get(codename='change_file')
        delete_file = Permission.objects.get(codename='delete_file')
        add_file = Permission.objects.get(codename='add_file')

        can_edit_file_perm, _ = Permission.objects.get_or_create(
            codename='can_edit_file',
            name='Can edit file',
            content_type=file_content_type
        )

        # User model permissions
        view_user = Permission.objects.get(codename='view_user')
        change_user = Permission.objects.get(codename='change_user')
        delete_user = Permission.objects.get(codename='delete_user')

    except ObjectDoesNotExist:
        return

    # Create groups
    director_group, _ = Group.objects.get_or_create(name='Director')
    manager_group, _ = Group.objects.get_or_create(name='Manager')
    staff_group, _ = Group.objects.get_or_create(name='Staff')
    customer_group, _ = Group.objects.get_or_create(name='Customer')

    # Assign permissions to groups
    director_group.permissions.set([
        view_file, change_file, delete_file, add_file, can_edit_file_perm,
        view_user, change_user, delete_user
    ])

    manager_group.permissions.set([
        view_file, change_file, add_file,
        view_user, change_user
    ])

    staff_group.permissions.set([
        view_file, add_file,
        view_user
    ])

    customer_group.permissions.set([view_file, view_user])

    # Add permission for file access logs view
    file_access_log_permission, created = Permission.objects.get_or_create(
        codename='view_fileaccesslog',
        name='Can view file access logs',
        content_type=ContentType.objects.get_for_model(FileAccessLog)
    )

    # Assign the permission to the appropriate groups
    director_group.permissions.add(file_access_log_permission)
    manager_group.permissions.add(file_access_log_permission)

    # Explicitly assign this permission to all superusers
    superusers = User.objects.filter(is_superuser=True)
    for user in superusers:
        user.user_permissions.add(file_access_log_permission)



@receiver(post_save, sender=User)
def assign_permissions_based_on_group(sender, instance, created, **kwargs):
    """
    Signal handler that assigns permissions dynamically based on the user's group.
    """
    if created:
        # Create user profile if it does not exist
        Profile.objects.create(user=instance)
        
        # Assign group and permissions based on user role
        if instance.is_superuser:
            # Superuser automatically gets all permissions
            admin_group, _ = Group.objects.get_or_create(name='Admin')
            instance.groups.add(admin_group)
            assign_all_permissions(instance)
        else:
            # Assign specific group based on role or user type
            if instance.groups.filter(name='Director').exists():
                assign_director_permissions(instance)
            elif instance.groups.filter(name='Manager').exists():
                assign_manager_permissions(instance)
            elif instance.groups.filter(name='Staff').exists():
                assign_staff_permissions(instance)
    else:
        # If the user is updated, you might want to reassign permissions in case their group changed
        if hasattr(instance, 'profile'):
            instance.profile.save()

    # Ensure profile save operation (can be merged with the above signal)
    instance.profile.save()


def assign_all_permissions(user):
    """Assigns all permissions to the user (for superusers or Admin)"""
    permissions = Permission.objects.all()
    user.user_permissions.set(permissions)

def assign_director_permissions(user):
    """Assigns director-specific permissions to the user"""
    permissions = [
        'view_file',
        'change_file',
        'delete_file',
        'add_file',
        'view_user',
        'change_user',
        'delete_user',
    ]
    assign_permissions(user, permissions)

def assign_manager_permissions(user):
    """Assigns manager-specific permissions to the user"""
    permissions = [
        'view_file',
        'change_file',
        'add_file',
        'view_user',
        'change_user',
    ]
    assign_permissions(user, permissions)

def assign_staff_permissions(user):
    """Assigns staff-specific permissions to the user"""
    permissions = [
        'view_file',
        'add_file',
        'view_user',
    ]
    assign_permissions(user, permissions)

def assign_permissions(user, permissions_list):
    """Helper function to assign a list of permissions to a user"""
    for codename in permissions_list:
        try:
            permission = Permission.objects.get(codename=codename)
            user.user_permissions.add(permission)
        except Permission.DoesNotExist:
            print(f"⚠️ Permission with codename '{codename}' does not exist.")

@receiver(post_save, sender=Ticket)
def log_ticket_update(sender, instance, created, **kwargs):
    if created:
        return  # Skip logging new tickets

    old_ticket = getattr(instance, '_old_ticket', None)
    changes = []

    if old_ticket:
        # Status change
        if old_ticket.status != instance.status:
            changes.append(f"Status: {old_ticket.status} → {instance.status}")

        # Assigned to change
        if old_ticket.assigned_to != instance.assigned_to:
            old_assignee = old_ticket.assigned_to.username if old_ticket.assigned_to else "None"
            new_assignee = instance.assigned_to.username if instance.assigned_to else "None"
            changes.append(f"Assigned to: {old_assignee} → {new_assignee}")

    # Default generic update if no field-specific changes
    action = " | ".join(changes) if changes else f"Ticket updated: {instance.title}"

    ActivityLog.objects.create(
        ticket=instance,
        action=action,
        user=instance.updated_by
    )


@receiver(post_save, sender=TicketComment)
def log_ticket_comment(sender, instance, created, **kwargs):
    if not created:
        return

    # Use the actual field on your TicketComment model
    comment_text = getattr(instance, "comment", None) or getattr(instance, "content", None) or ""
    preview = (comment_text[:120] + "…") if len(comment_text) > 120 else comment_text

    action = f"Comment added to ticket {instance.ticket.title}: {preview}"

    ActivityLog.objects.create(
        ticket=instance.ticket,
        action=action,
        user=instance.created_by
    )


@receiver(post_save, sender=Ticket)
def log_ticket_resolution(sender, instance, created, **kwargs):
    if instance.status == 'Resolved':  # You can check your ticket status values
        action = f"Ticket resolved: {instance.title}"
        ActivityLog.objects.create(ticket=instance, action=action, user=instance.updated_by)