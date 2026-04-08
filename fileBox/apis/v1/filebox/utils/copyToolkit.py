import copy
from django.db.models import Sum
from django.db.models import Q, F, Value
from django.db import transaction
from Backend.models import FileFolderModel

def calculate_total_space_required(source_record_instance):
   if source_record_instance:   
        path_prefix_for_child = f"{source_record_instance.path or ''}/{source_record_instance.pk}".strip("/")   #strip is used to remove the slashs at the begining and end
        total_sum_of_the_size = FileFolderModel.objects.filter(
        Q(pk=source_record_instance.pk) | Q(path__startswith=path_prefix_for_child)
        ).aggregate(total_size=Sum('size'))['total_size'] or 0

        #aggregate is a SQL method used to perform calculations over a column and return a single value

        return total_sum_of_the_size
   else:
       return 0
   