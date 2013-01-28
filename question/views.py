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
from django.core.context_processors import csrf
from django.contrib.auth.decorators import login_required
from django.shortcuts import (render_to_response, redirect, RequestContext,
                              HttpResponse)


# 3rd party imports

# Our imports
from models import (QSet, QActual)
from person.models import Token, Timing
from course.models import Course
from logitem.views import create_hit

logger = logging.getLogger('quest')
logger.debug('Initializing quest::question::views.py')


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


def validate_user(request, course_code_slug, question_set_slug,
                  question_id=None, admin=False, expiry_check=True):
    """
    Some validation code that is common to functions below.
    """
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

    token = request.session['token']
    token_obj = Token.objects.filter(token_address=token).filter(user=user)
    if not token_obj:
        logger.info('Bad token used: [%s]; request path="%s"' %
                    (token, request.path_info))
        return redirect('quest-main-page')

    if token_obj[0].has_been_used:
        logger.info('Token used: [%s]; session token="%s"' %
                    (request.path_info, request.session['token']))
        page_content = {}
        return render_to_response('person/invalid-expired-token.html',
                                  page_content)

    if request.session['token'] != token:
        logger.info('Token mismatch: [%s]; session token="%s"' %
                    (request.path_info, request.session['token']))
        return redirect('quest-main-page')

    if expiry_check and not(admin):
        t_objs = Timing.objects.filter(user=request.user.profile, qset=qset)
        if t_objs:
            old_time = t_objs[0].final_time
        else:
            old_time = datetime.datetime(1901, 1, 1, 0, 0, 0)
        expiry_time = request.session.get('expires', old_time)

        #if False:
        # this is clearly not the only criterion: we must handle whether
        # the user can see previous qset's and also check the current qset's
        # expiry time. Not solely rely on t_objs
        if expiry_time  < datetime.datetime.now():
            # Either the user doesn't have the expiry date set in their
            # session (i.e. they logged out and then refreshed the page)
            # or the expiry has past the current time
            exp = expiry_time.strftime('%H:%M:%S on %d %h %Y')
            ctxdict = {'time_expired': exp,
                       'solution_time': qset[0].ans_time_final}
            ctxdict.update(csrf(request))
            return render_to_response('question/time-expired.html', ctxdict,
                                      context_instance=RequestContext(request))

    # Return all the questions for this user
    if admin:
        # Admin users only (ab)use this function to get the course and
        # question set objects, as well as to validate the admin user
        return courses[0], qset[0]
    else:
        quests = QActual.objects.filter(qset=qset[0]).filter(user=user)

    if len(quests) == 0:
        # I've seen this error only occur once; when the URL for the questions
        # was displayed and I came back the next day and click on the links
        # it crashed because len(quests) = 0, but i can't reproduce it.
        # However, it is sensible to verify this, because if the use is trying
        # to view a qset for which there are no quests, then there is nothing
        # to display.
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
def ask_question_set(request):        # URL: ``quest-question-set``
    """
    Ask which question set to display
    """
    user = request.user.profile
    qsets = []
    idx = 0
    qsets.append([])
    for course in user.courses.all():
        # Which course(s) is the user registered for? Get all QSet's for them
        qsets[idx].extend(course.qset_set.order_by('-ans_time_start'))
        idx += 1

    # Show question sets
    ctxdict = {'question_set_list': qsets,
               'username': user.user.first_name + ' ' + user.user.last_name,
               #'last_login': request.user.last_login <-- useless
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
    quests = validate_user(request, course_code_slug, question_set_slug,
                           expiry_check=False)
    if  isinstance(quests, HttpResponse):
        return quests
    if isinstance(quests, tuple):
        quests, _ = quests

    min_remain = 0
    sec_remain = 0

    # Information to store
    if not quests:
        raise NotImplementedError(('Should not be able to click link if the '
                                   'questions are not available yet.'))

    qset = quests[0].qset
    # Has the user started this QSet already? If not, create a DB entry
    # NOTE: there can only be one DB entry per user per Qset
    exist = Timing.objects.filter(user=request.user.profile, qset=qset)
    start_time = datetime.datetime.now()
    if exist:
        final_time = exist[0].final_time
    else:
        done_timing = False

        # Test has not started yet
        if qset.ans_time_start.replace(tzinfo=None) \
                                                > datetime.datetime.now():

            ctxdict = {'time_to_start': qset.ans_time_start}
            ctxdict.update(csrf(request))
            return render_to_response('question/not-started-yet.html',
                        ctxdict, context_instance=RequestContext(request))

        # Test has finished: give the user 60 mins to review the solutions
        # after that they need to sign in again.
        if qset.ans_time_final.replace(tzinfo=None) \
                                               <= datetime.datetime.now():
            final_time = datetime.datetime.now() + \
                                   datetime.timedelta(seconds=60*60)
            done_timing = True

        if not done_timing:
            # User is signing in during the test time frame and they have
            # not signed in before. How much time remaining = min(test
            # duration, test cut off-time)
            final = qset.max_duration
            right_now = datetime.datetime.now()
            indend_finish = right_now + \
                            datetime.timedelta(hours=final.hour) + \
                            datetime.timedelta(minutes=final.minute) + \
                            datetime.timedelta(seconds=final.second)

            if qset.max_duration == datetime.time(0, 0, 0):
                final_time = quests[0].qset.ans_time_final
            else:
                final_time = min(indend_finish,
                    quests[0].qset.ans_time_final)

            token = request.session['token']
            token_obj = Token.objects.filter(token_address=token)
            Timing.objects.create(user=request.user.profile, qset=qset,
                                  start_time=start_time,
                                  final_time=final_time,
                                  token=token_obj[0])

    request.session['expires'] = final_time
    request.session.save()

    exist = Timing.objects.filter(user=request.user.profile, qset=qset)
    if exist:
        final_time = exist[0].final_time
    else:
        final_time = quests[0].qset.ans_time_final

    now_time = datetime.datetime.now()
    if final_time > now_time:        # The testing period is running
        delta = final_time - now_time
        min_remain = int(floor(delta.seconds/60.0))
        sec_remain = int(delta.seconds - min_remain*60)

    # Topics:
    tags = set()
    for item in quests:
        for tag in item.qtemplate.tags.all():
            tags.add(tag)

    # Now display the questions
    ctxdict = {'quest_list': quests,   # list of QActual items
               'course': course_code_slug,
               'qset': question_set_slug,
               'minutes_left': min_remain,
               'seconds_left': sec_remain,
               'tag_list': list(tags)}
    ctxdict.update(csrf(request))
    return render_to_response('question/question-list.html', ctxdict,
                              context_instance=RequestContext(request))

@login_required                          # URL: ``quest-ask-specific-question``
def ask_specific_question(request, course_code_slug, question_set_slug,
                              question_id):
    """
    Asks a specific question to the user.
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
                    val = token_dict[item.group(2)]
                    out += '%s%s%s%s%s%s' %\
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


    qset = quests[0].qset
    now_time = datetime.datetime.now()
    exist = Timing.objects.filter(user=request.user.profile, qset=qset)
    min_remain = 0
    sec_remain = 0
    if exist:
        final_time = exist[0].final_time
        if final_time > now_time:
            delta = final_time - now_time
            min_remain = int(floor(delta.seconds/60.0))
            sec_remain = int(delta.seconds - min_remain*60)

    final_time = quest.qset.ans_time_final.replace(tzinfo=None)

    if final_time > now_time:                  # The testing period is running
        html_solution = ''                      # don't show the solutions yet
    else:
        html_solution = quest.html_solution

        # Make the inputs disabled when displaying solutions:
        html_question = re.sub(r'<input', r'<input disabled="true"',
                                html_question)

        if q_type in ('long'):
            html_question = re.sub(r'<textarea', r'<textarea disabled="true"',
                                html_question)

    ctxdict = {'quest_list': quests,
               'item_id': q_id,
               'course': course_code_slug,
               'qset': question_set_slug,
               'item': quest,
               'timeout_time': 500,       # in the HTML template, XHR timeout
               'minutes_left': min_remain,
               'seconds_left': sec_remain,
               'html_question': html_question,
               'html_solution': html_solution,
               'last_question': q_id==len(quests)}
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
    The user is submitting their final answer.
    """
    quests = validate_user(request, course_code_slug, question_set_slug,
                            question_id)
    if isinstance(quests, HttpResponse):
        return quests
    if isinstance(quests, tuple):
        quests, q_id = quests


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
    #timing = Timing.objects.filter(token=token)
    #if timing:
        #timing[0].is_valid = False
        #timing[0].save()

    try:
        del request.session['expires']
    except KeyError:
        pass
    request.session.save()  # consider using SESSION_SAVE_EVERY_REQUEST=True

    user = request.user.profile
    final = quests[0].qset.ans_time_final.strftime('%H:%M:%S on %d %h %Y')
    token_obj = Token.objects.filter(token_address=token).filter(user=user)

    # TODO(KGD): should we check we have a token_obj[0]
    token_obj[0].has_been_used = True
    token_obj[0].save()
    #_ = Token.objects.update(id=token_obj[0].id, user=user.user,
    #                         has_been_used=True,
    #                         token_address=token_obj[0].token_address)
    ctxdict = {'token': token,
               'quest_cut_off': final}
    return render_to_response('question/successfully-submitted.html', ctxdict,
                                context_instance=RequestContext(request))
