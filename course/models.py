from django.db import models
from django.template.defaultfilters import slugify
from django.core.exceptions import ValidationError

class Course(models.Model):
    """
    Define course related items.
    """
    # Full course name
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)  # shorter course code
    slug = models.SlugField(max_length=20, editable=False)

    def __unicode__(self):
        return self.code

    def save(self, *args, **kwargs):
        """ Slug is a primary key: don't save a new tag if one already exists
        with the identical slug.
        """
        slug = slugify(self.name)

        # happens if the slug is totally unicode characters
        if len(slug) == 0:
            raise ValidationError('Course slug contains invalid characters')

        if Course.objects.filter(slug=slug):
            return
        else:
            # Call the "real" save() method.
            self.slug = slug
            super(Course, self).save(*args, **kwargs)