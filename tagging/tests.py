# -*- coding: utf-8 -*-

from django.test import TestCase
from models import Tag
from django.core.exceptions import ValidationError

class RepeatedTag(TestCase):
    def test_adding_repeated_tag(self):
        """
        Tests that tags are unique based on their slug, without creating a
        new tag object.
        """
        # Always use ``get_or_create(...)`` rather than relying on
        # ``create(...)`` to return a valid tag.
        t1, _ = Tag.objects.get_or_create(name='testing tag')
        t2, _ = Tag.objects.get_or_create(name='testing tag')
        self.assertEqual(t1.id, t2.id)

    def unicode_tags(self):
        self.assertRaises(ValidationError, Tag.objects.get_or_create,
                          name='さようなら')
