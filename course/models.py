from django.db import models
from django.template.defaultfilters import slugify
from django.core.exceptions import ValidationError

class Course(models.Model):
    """
    Define course related items.
    """
    year_choice = (('2012/2013','2012/2013'),
                   ('2013/2014','2013/2014'),
                   ('2014/2015','2014/2015'),
                   ('2015/2016','2015/2016'),

    )
    # Full course name
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)  # shorter course code
    slug = models.SlugField(max_length=100, editable=False)
    year = models.CharField(verbose_name='Academic year', choices=year_choice,
                            max_length=20, default='2014/2015')

    def __unicode__(self):
        return '%s [%s]' % (self.code, self.year)

    def save(self, *args, **kwargs):
        """ Slug is a primary key: don't save a new tag if one already exists
        with the identical slug.
        """
        slug = slugify('%s %s' % (self.name, self.year.replace('/', '-')))

        # happens if the slug is totally unicode characters
        if len(slug) == 0:
            raise ValidationError('Course slug contains invalid characters')

        if Course.objects.filter(slug=slug):
            raise ValidationError('Course slug already exists')
        else:
            # Call the "real" save() method.
            self.slug = slug
            super(Course, self).save(*args, **kwargs)
