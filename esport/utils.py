from django.core.files.storage import FileSystemStorage
from django.conf import settings

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

def normalize_team_name(name):
    name = name.strip()

    if name == "TT":
        name = "ThunderTalk Gaming"
    name = name.lower()
    name = name.replace("'", "").replace("'", "").replace("`", "")
    # Normalise les accents
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    # Normalise les espaces (ne les supprime PAS — conserve la lisibilité pour difflib)
    name = re.sub(r"\s+", " ", name).strip()
    # Retire les préfixes génériques
    name = re.sub(r"^(movistar|team|esports|gaming|club|fc|ac|the|-)\s+", "", name)
    return name

if settings.USE_S3 if hasattr(settings, 'USE_S3') else False:
    from storages.backends.s3boto3 import S3BotoStorage
    class OverwriteStorage(s3Boto3Storage):
        def get_available_name(self, name, max_length=None):
            try:
                if self.exists(name):
                    self.delete(name)
                except Exception:
                    pass
                return name
else:
    from django.core.files.storage import FileSystemStorage
    class OverwriteStorage(FileSystemStorage):
        def get_available_name(self, name, max_length=None):
            try:
                if self.exists(name):
                    self.delete(name)
                except Exception:
                    pass
                return name