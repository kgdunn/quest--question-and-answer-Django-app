# -*- coding: utf-8 -*-

# Python and Django imports
import re
import logging
import datetime
try:
    import simplejson as json
except ImportError:
    import json

from math import floor
from django.db.models.query import QuerySet
from django.core.context_processors import csrf
from django.contrib.auth.decorators import login_required
from django.shortcuts import (render_to_response, redirect, RequestContext,
                              HttpResponse)

# 3rd party imports

# Our imports
from models import (QSet, QActual)
from person.models import Token, Timing
from course.models import Course
from stats.views import create_hit, get_profile
from stats.models import TimerStart
from utils import grade_display
logger = logging.getLogger('quest')


class BadVariableSpecification(Exception): pass

# TODO(KGD): allow these to be case-insenstive later on
CONTRIB_RE = re.compile(r'^Contributor:(\s*)(.*)$')
TAGS_RE = re.compile(r'^Tags:(\s*)(.*)$')
DIFFICULTY_RE = re.compile(r'^Difficulty:(\s*)(.*)$')
GRADES_RE = re.compile(r'^Grade:(\s*)(.*)$')
FEEDBACK_RE = re.compile(r'^Feedback:(\s*)(.*)$')

LURE_RE = re.compile(r'^\&(\s*)(.*)$')
KEY_RE = re.compile(r'^\^(\s*)(.*)$')
FINAL_RE = re.compile(r'^\&(\s*)(.*)$')

TEXTAREA_RE = re.compile(r'\<textarea (.*?)\>(?P<filled>.*?)\</textarea\>')
INPUT_RE = re.compile(r'\<input(.*?)name="(.*?)"(.*?)\</input\>')

class ParseError(Exception):
    pass


def get_questions_for_user(qset, user):
    """
    Returns the QActual objects for a specific question set (quiz) for a
    specific user. Use this function, because it is called elsewhere.
    """
    if isinstance(qset, QuerySet):
        q = qset[0]
    else:
        q = qset

    return QActual.objects.filter(qset=q).filter(user=user).order_by('id')


def validate_user(request, course_code_slug, question_set_slug,
                  question_id=None, admin=False):
    """
    Some validation code that is common to functions below. Only validates
    authentication (not authorization).
    """
    if admin and course_code_slug=='None' and question_set_slug=='None':
        #return Quest.objects.filter
        assert(False)  # I'm not sure what was intended by the prior line
    user = request.user.profile
    courses = Course.objects.filter(slug=course_code_slug)
    if not courses:
        logger.info('Bad course code request: [%s]; request path="%s"' %
                    (course_code_slug, request.path_info))
        return redirect('quest-main-page')

    qset=QSet.objects.filter(slug=question_set_slug).filter(course=courses[0])
    if not qset:
        logger.info('Bad question set request: [%s]; request path="%s"' %
                    (question_set_slug, request.path_info))
        return redirect('quest-main-page')
    else:
        if not qset[0].is_active:
            logger.warn('Attempt by user "%s" to access in-active QSet [%s]' %
                        (user, question_set_slug))
            return redirect('quest-main-page')

    if not admin:
        token = request.session.get('token', '')
        token_obj = Token.objects.filter(token_address=token).filter(user=user)
        if not token_obj:
            logger.info('Bad token used: [%s]; request path="%s"' %
                        (token, request.path_info))
            return redirect('quest-main-page')

        if token_obj[0].has_been_used:
            logger.info('Token used: [%s]; session token="%s"' %
                        (request.path_info, token))
            page_content = {}
            return render_to_response('person/invalid-expired-token.html',
                                      page_content)

        if request.session['token'] != token:
            logger.info('Token mismatch: [%s]; session token="%s"' %
                        (request.path_info, request.session['token']))
            return redirect('quest-main-page')

    # Return all the questions for this user
    if admin:
        # Admin users only (ab)use this function to get the course and
        # question set objects, as well as to validate the admin user
        return courses[0], qset[0]
    else:
        quests = get_questions_for_user(qset, user)


    if len(quests) == 0:
        # I've seen this error only occur once; when the URL for the questions
        # was displayed and I came back the next day and click on the links
        # it crashed because len(quests) = 0, but i can't reproduce it.
        # However, it is sensible to verify this, because if the use is trying
        # to view a qset for which there are no quests, then there is nothing
        # to display.
        # This has also occured when a user has been added to a course by
        # mistake (i.e. no quests have been generated for the user, since they
        # were retroactively added to the course, after quest generation)
        logger.info('No quests for token [%s]; URL [%s]' %
                    (token_obj[0], request.path_info))
        return redirect('quest-main-page')

    q_id = question_id
    if question_id:
        try:
            q_id = int(question_id)
        except ValueError:
            logger.info('Bad question number request: [%s]; request path="%s"'
                    % (question_id, request.path_info))
            return redirect('quest-main-page')

        if q_id < 1 or q_id > len(quests):
            logger.info('Bad question integer request: [%s]; request path='
                        '"%s"' % (question_id, request.path_info))
            return redirect('quest-ask-show-questions', course_code_slug,
                            question_set_slug)

    if question_id:
        return (quests, q_id)
    else:
        return quests

@login_required
def course_selection(request):        # URL: ``quest-course-selection``
    """
    User picks for which course they want to answer questions
    """
    user = request.user.profile

    ctxdict = {'course_list':  user.courses.all(),
               'username': user.user.first_name + ' ' + user.user.last_name,
              }
    ctxdict.update(csrf(request))
    return render_to_response('question/course-selection.html', ctxdict,
                              context_instance=RequestContext(request))

@login_required                          # URL: ``quest-question-set``
def ask_question_set(request, course_code_slug):
    """
    Ask which question set to display
    """
    user = request.user.profile
    qsets = list()
    course = Course.objects.filter(slug=course_code_slug)
    if len(course) != 1:
        return redirect('quest-course-selection')
    else:
        course = course[0]

    average = None  # in case user is not registered in any courses
    qsets.extend(course.qset_set.order_by('-ans_time_start'))
    grade = 0.0
    iterate = 0
    for iterate, item in enumerate(qsets):
        qsets[iterate].grade, actual, max_grade = \
                                           grades_for_quest(item, user)
        if max_grade > 0.0:
            grade += actual / (max_grade + 0.0)
        else:
            grade = 0.0

    # Calculate the average afterwards
    average = grade / float(iterate+1) * 100

    # Log it
    TimerStart.objects.create(event='show-all-course-quests',
                              user=user,
                              profile=get_profile(request),
                              item_pk=course.id,
                              item_type='Course',
                              referrer=request.META.get('HTTP_REFERER', ''))

    # Show question sets
    ctxdict = {'question_set_list': qsets,
               'username': user.user.first_name + ' ' + user.user.last_name,
               'average': average,
              }
    ctxdict.update(csrf(request))
    return render_to_response('question/question-sets.html', ctxdict,
                              context_instance=RequestContext(request))

@login_required                          # URL: ``quest-ask-show-questions``
def ask_show_questions(request, course_code_slug, question_set_slug):
    """
    Display questions (and perhaps answers) to questions from a question set
    for a specific user
    """
    quests = validate_user(request, course_code_slug, question_set_slug)
    if  isinstance(quests, HttpResponse):
        return quests
    if isinstance(quests, tuple):
        quests, _ = quests

    # Information to store
    if not quests:
        raise NotImplementedError(('Should not be able to click link if the '
                                   'questions are not available yet.'))

    # Topics covered in this question set
    tags = set()
    for item in quests:
        for tag in item.qtemplate.tags.all():
            tags.add(tag)


    # First send them off to sign the honesty statement
    if not request.session.get('honesty_check', ''):
        ctxdict = {'qset': quests[0].qset,
                   'course': Course.objects.filter(slug=course_code_slug)[0]}
        ctxdict.update(csrf(request))
        request.session['honesty_check'] = True
        request.session.save()
        return render_to_response('question/honesty-check.html',
                    ctxdict, context_instance=RequestContext(request))

    # The second time through this function ... display the questions
    ctxdict = {'quest_list': quests,   # list of QActual items
               'course': course_code_slug,
               'qset': question_set_slug,
               #'minutes_left': min_remain,
               #'seconds_left': sec_remain,
               'tag_list': list(tags),
               'grade_str': grades_for_quest(quests)[0],
               }
    ctxdict.update(csrf(request))
    return render_to_response('question/question-list.html', ctxdict,
                              context_instance=RequestContext(request))

@login_required                          # URL: ``quest-ask-specific-question``
def ask_specific_question(request, course_code_slug, question_set_slug,
                              question_id):
    """
    Asks a specific question to the user.

    There is also extensive validation done in this function.
    """
    quests = validate_user(request, course_code_slug, question_set_slug,
                                 question_id)
    if isinstance(quests, HttpResponse):
        return quests
    if isinstance(quests, tuple):
        quests, q_id = quests

    quest = quests[q_id-1]
    create_hit(request, quest, extra_info=None)
    html_question = quest.as_displayed
    q_type = quest.qtemplate.q_type

    # Has the user answered this question (even temporarily?).
    if quest.given_answer:

        if q_type in ('mcq', 'tf'):
            html_question = re.sub(r'"'+quest.given_answer+r'"',
                                r'"'+quest.given_answer+r'" checked',
                                html_question)

        if q_type in ('multi', ):
            for selection in quest.given_answer.split(','):
                html_question = re.sub(r'"'+selection+r'"',
                                                r'"'+selection+r'" checked',
                                                html_question)

        if q_type in ('long'):
            re_exp = TEXTAREA_RE.search(html_question)
            if re_exp:
                html_question = '%s%s%s' % (html_question[0:re_exp.start(2)],
                                            quest.given_answer,
                                            html_question[re_exp.end(2):])

        if q_type in ('short'):
            out = ''
            if INPUT_RE.findall(html_question):
                # INPUT_RE = (r'\<input(.*?)name="(.*?)"(.*?)\</input\>')
                start = 0
                token_dict = json.loads(quest.given_answer)
                for item in INPUT_RE.finditer(html_question):
                    val = token_dict.get(item.group(2), '')
                    out += '%s%s%s%s%s%s' % \
                            (html_question[start:item.start()],
                             r'<input',
                             ' value="%s"' % val,
                             ' name="%s"' % item.group(2),
                             item.group(3),
                             r'</input>')

                    start = item.end()

                if out:
                    out += html_question[start:]

                html_question = out


    # Validation types:
    show_solution = show_question = False
    fields_disabled = True
    event_type = ''
    other_info = ''
    item_pk = quest.id
    item_type = 'QActual'
    min_remain = sec_remain = 0
    course = Course.objects.filter(slug=course_code_slug)[0]
    qset = quests[0].qset
    now_time = datetime.datetime.now()

    if qset.ans_time_start.replace(tzinfo=None) > now_time:
        # Test has not started yet; throw "too-early"
        show_question = False

    elif qset.ans_time_final.replace(tzinfo=None) <= now_time:
        # Test is finished; show the questions, fields disabled, with solutions
        show_solution = True
        show_question = True
        final_time = now_time + datetime.timedelta(seconds=60*60)

    else:
        # We are in the middle of the QSet testing period: show question but
        # no solution.
        # Check for a Timing object.
        #    If present,
        #        Are we within the USERS time window
        #           Y : allow question to be answered
        #           N : throw error: time has expired.
        #    If not present:
        #        create one

        show_question = True
        fields_disabled = False

        timing_obj = Timing.objects.filter(user=request.user.profile, qset=qset)
        if timing_obj:
            tobj = timing_obj[0]
	    event_type = 'attempting-quest'

            if tobj.final_time <= now_time:
                # Either the user doesn't have the expiry date set in their
                # session (i.e. they logged out and then refreshed the page)
                # or the expiry has past the current time
                exp = tobj.final_time.strftime('%H:%M:%S on %d %h %Y')
                ctxdict = {'time_expired': exp,
                           'solution_time': qset.ans_time_final}
                ctxdict.update(csrf(request))
                return render_to_response('question/time-expired.html',
                                    ctxdict,
                                    context_instance=RequestContext(request))

        else:
            # Create the timing object, starting from right now
            final = qset.max_duration
            indend_finish = now_time + \
                            datetime.timedelta(hours=final.hour) + \
                            datetime.timedelta(minutes=final.minute) + \
                            datetime.timedelta(seconds=final.second)

            if qset.max_duration == datetime.time(0, 0, 0):
                # Not sure why this is checked; guess it is incase the admin
                # user has forgot to specify the maximum time duration
                final_time = qset.ans_time_final
            else:
                # Finish before the test if over, or earlier
                final_time = min(indend_finish, qset.ans_time_final)

            token = request.session.get('token', None)
            if token:
		event_type = 'start-a-quest-session'
		other_info = 'Starting QSet; creating Timing object'
                token_obj = Token.objects.filter(token_address=token)
                tobj = Timing.objects.create(user=request.user.profile,
                                             qset=qset,
                                             start_time=now_time,
                                             final_time=final_time,
                                             token=token_obj[0])


        if tobj.final_time > now_time:
            delta = tobj.final_time - now_time
            min_remain = int(floor(delta.seconds/60.0))
            sec_remain = int(delta.seconds - min_remain*60)


    # Now perform various actions depending on the authorizations above
    if not(show_question):
        ctxdict = {'time_to_start': qset.ans_time_start}
        ctxdict.update(csrf(request))
        return render_to_response('question/not-started-yet.html',
                    ctxdict, context_instance=RequestContext(request))

    if fields_disabled:
        # Make the inputs disabled when displaying solutions:
        html_question = re.sub(r'<input', (r'<input disabled="true" '
                               r'style="color: #B00"'), html_question)

        if q_type in ('long'):
            html_question = re.sub(r'<textarea', r'<textarea disabled="true"',
                                html_question)

    if show_solution:
	event_type = 'review-a-quest-question-post'
	other_info = 'Token = %s' % request.session.get('token', '')
        html_solution = quest.html_solution

    else:
	other_info = 'QActual=[%d]; current answer: %s' % \
	                                (quest.id, quest.given_answer[0:4999])
        html_solution = ''                      # don't show the solutions yet


    if event_type:
	TimerStart.objects.create(event=event_type,
	                user=request.user.profile,
	                profile=get_profile(request),
	                item_pk=item_pk,
	                item_type=item_type,
	                referrer=request.META.get('HTTP_REFERER', '')[0:510],
	                other_info=other_info)
    else:
	pass


    ctxdict = {'quest_list': quests,
               'item_id': q_id,
               'course_name': course,
               'course': course_code_slug,
               'qset_name': qset.name,
               'qset': question_set_slug,
               'item': quest,
               'timeout_time': 500,       # in the HTML template, XHR timeout
               'minutes_left': min_remain,
               'seconds_left': sec_remain,
               'html_question': html_question,
               'html_solution': html_solution,
               'last_question': q_id==len(quests)
               }
    ctxdict.update(csrf(request))
    return render_to_response('question/single-question.html', ctxdict,
                              context_instance=RequestContext(request))

@login_required                          # URL: ``quest-submit-final-check``
def submit_answers(request, course_code_slug, question_set_slug):
    """
    Obtain the finalized user answers and store them permanently.
    """
    quests = validate_user(request, course_code_slug, question_set_slug)
    if isinstance(quests, HttpResponse):
        return quests
    if isinstance(quests, tuple):
        quests, _ = quests

    ctxdict = {'quest_list': quests,
                'course': course_code_slug,
                'qset': question_set_slug,
                'error_message': ''}
    ctxdict.update(csrf(request))

    if request.POST:
        if request.POST.get('honesty-statement', 'NOT_CHECKED') == 'agreed':
            return redirect('quest-successful-submission', course_code_slug,
                            question_set_slug)
        else:
            ctxdict['error_message'] = 'The work submitted must be your own'
            return render_to_response('question/final-honesty-check.html',
                                    ctxdict,
                                    context_instance=RequestContext(request))
    else:
        return render_to_response('question/final-honesty-check.html',
                                    ctxdict,
                                    context_instance=RequestContext(request))

@login_required                          # URL: ``quest-store-answer``
def store_answer(request, course_code_slug, question_set_slug, question_id):
    """
    The user is submitting an answer.
    """
    quests = validate_user(request, course_code_slug, question_set_slug,
                            question_id)
    if isinstance(quests, HttpResponse):
        # Rather show this if the user isn't validated
        return HttpResponse('Please sign in again; answer <b>NOT recorded</b>')

    if isinstance(quests, tuple):
        quests, q_id = quests

    qset = quests[0].qset
    now_time = datetime.datetime.now()
    invalid_response = False
    if qset.ans_time_start.replace(tzinfo=None) > now_time:
	# Invalid to have an answer before the starting time
        invalid_response = True

    elif qset.ans_time_final.replace(tzinfo=None) <= now_time:
	# Invalid to have an answer after the ending time
        invalid_response = True

    else:
        # We are in the middle of the QSet testing period. There must be a
	# Timing object. Are we within the USERS time window?
        #    Y : allow question to be answered
        #    N : throw error: time has expired.

        timing_obj = Timing.objects.filter(user=request.user.profile, qset=qset)
        if timing_obj:
            tobj = timing_obj[0]
            if tobj.final_time <= now_time:
                invalid_response = True
	    else:
		# The only valid condition under which we should be recording
		# answers to questions. Any other path through this function
		# indicates an attempt at hacking the system.
		invalid_response = False
        else:
            invalid_response = True

    if invalid_response:
	logger.warn('Hacking attempt: [user: %s] [profile: %s]' %
	        (request.user.profile, request.session.get('profile', '')))
	return HttpResponse('')

    quest = quests[q_id-1]
    if quest.qtemplate.q_type == 'short':
        keys = request.GET.keys()
        try:
            keys.remove('_')
        except ValueError:
            pass
        out = {}
        for key in keys:
            out[key] = request.GET[key]

        quest.given_answer = json.dumps(out, sort_keys=True)
    elif request.GET.has_key('entered'):
        quest.given_answer = request.GET['entered']


    quest.is_submitted = False
    quest.save()

    return HttpResponse('%s: Answer recorded' %
                        datetime.datetime.now().strftime('%H:%M:%S'))

@login_required                          # URL: ``quest-successful-submission``
def successful_submission(request, course_code_slug, question_set_slug):
    """
    User has successfully saved their answers.
    """
    quests = validate_user(request, course_code_slug, question_set_slug)
    if isinstance(quests, HttpResponse):
        return quests

    # Mark every question as successfully submitted
    for quest in quests:
        quest.is_submitted = True
        quest.save()

    if quests:
        create_hit(request, quests[0].qset, extra_info='Submitted answers')

    token = request.session['token']

    user = request.user.profile
    final = quests[0].qset.ans_time_final.strftime('%H:%M:%S on %d %h %Y')
    token_obj = Token.objects.filter(token_address=token).filter(user=user)

    if token_obj:
	token_obj[0].has_been_used = True
	token_obj[0].save()

    TimerStart.objects.create(event='submit-qset',
                              user=user,
                              profile=get_profile(request),
                              item_pk=quests[0].qset.id,
                              item_type='QSet',
                              referrer=request.META.get('HTTP_REFERER', ''))

    # TODO(KGD): send an email
    ctxdict = {'token': token,
               'quest_cut_off': final}
    return render_to_response('question/successfully-submitted.html', ctxdict,
                                context_instance=RequestContext(request))


def grades_for_quest(qactuals_or_qset, user=None):
    """
    Returns a string that shows the grades for the student, for their
    set of quests.
    """
    if isinstance(qactuals_or_qset, QSet):
        qactuals = QActual.objects.filter(qset=qactuals_or_qset, user=user)
    else:
        qactuals = qactuals_or_qset

    max_grade = 0.0
    actual_grade = 0.0
    show_grades = True  # only show grade if all questions are graded
    for item in qactuals:
        max_grade += item.qtemplate.max_grade
        if item.grade:
            actual_grade += item.grade.grade_value
        else:
            show_grades = False

    if show_grades:
        return grade_display(actual_grade, max_grade), actual_grade, max_grade
    else:
        return None, actual_grade, max_grade
