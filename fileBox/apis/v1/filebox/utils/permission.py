

from fileBox.Backend.models import FileFolderPermission


def grand_permission_for_shared_instance(ids , user , file_permission_instance):
    permissions = FileFolderPermission.objects.filter(fileFolder_Instance_id__in=ids , user_id = user).values_list('permission_type', flat=True)

    permission_mapping = {'VIEW': 1, 'EDIT': 2, 'ADMIN': 3}
    highest_permission = max([permission_mapping.get(p, 0) for p in permissions], default=0)


    return list(permission_mapping.keys())[list(permission_mapping.values()).index(highest_permission)] if highest_permission > 0 else file_permission_instance.permission_type,