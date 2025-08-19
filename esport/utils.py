
from django.core.files.storage import FileSystemStorage

class OverwriteStorage(FileSystemStorage):
    def get_available_name(self, name, max_length=None):
        # If the name already exists, delete it first so the new file can use the same name.
        try:
            if self.exists(name):
                self.delete(name)
        except Exception:
            # be tolerant of any delete errors
            pass
        return name
        
def get_possible_scores(match):
    bo = getattr(match, 'best_of', None)
    if bo == 1:
        return [(1, 0)]
    elif bo == 3:
        return [(2, 0), (2, 1)]
    elif bo == 5:
        return [(3, 0), (3, 1), (3, 2)]
    return []