# -*- coding: utf-8 -*-

# Python and Django imports
import re
import logging
import datetime
from django.core.context_processors import csrf
from django.contrib.auth.decorators import login_required
from django.shortcuts import (render_to_response, redirect, RequestContext,
                              HttpResponse)


# 3rd party imports

# Our imports
from models import (QSet, QActual)
from person.models import Token
from course.models import Course

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

class ParseError(Exception):
    pass


def validate_user(request, course_code_slug, question_set_slug,
                  question_id=None, admin=False):
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

    if request.session['expires'] < datetime.datetime.now():
        exp = request.session['expires'].strftime('%H:%M:%S on %d %h %Y')
        ctxdict = {'time_expired': exp}
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

    q_id = question_id
    if question_id:
        try:
            q_id = int(question_id)
        except ValueError:
            logger.info('Bad question number request: [%s]; request path="%s"'
                    % (question_id, request.path_info))
            return redirect('quest-main-page')

        if q_id < 1 or q_id > len(quests):
            logger.info('Bad question integer request: [%s]; request path="%s"' %
                        (question_id, request.path_info))
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
    ctxdict = {'question_set_list': qsets}
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

    # Now display the questions
    ctxdict = {'quests_lists': quests,
               'course': course_code_slug,
               'qset': question_set_slug}
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

    # TODO(KGD): Log start time of question (and end time of previous one)
    #times_displayed

    quest = quests[q_id-1]
    html_question = quest.as_displayed
    # Has the user answered this question (even temporarily?).
    if quest.given_answer:
        if quest.qtemplate.q_type in ('mcq', 'multi', 'tf'):

            html_question = re.sub(r'"'+quest.given_answer+r'"',
                                r'"'+quest.given_answer+r'" checked',
                                html_question)

    final_time = quest.qset.ans_time_final.replace(tzinfo=None)
    if final_time > datetime.datetime.now():   # The testing period is running
        html_solution = ''                      # don't show the solutions yet
    else:
        html_solution = quest.html_solution

        # Make the inputs disabled when displaying solutions:
        html_question = re.sub(r'<input', r'<input disabled="true"',
                                html_question)

    ctxdict = {'quests_lists': quests,
               'item_id': q_id,
               'course': course_code_slug,
               'qset': question_set_slug,
               'item': quest,
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

    ctxdict = {'quests_lists': quests,
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

    quests[q_id-1].given_answer = request.GET['entered']
    quests[q_id-1].is_submitted = False
    quests[q_id-1].save()

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

    token = request.session['token']
    user = request.user.profile
    final = quests[0].qset.ans_time_final.strftime('%H:%M:%S on %d %h %Y')
    token_obj = Token.objects.filter(token_address=token).filter(user=user)
    _ = Token.objects.update(id=token_obj[0].id, user=user.user,
                             has_been_used=True,
                             token_address=token_obj[0].token_address)
    ctxdict = {'token': token,
               'quest_cut_off': final}
    return render_to_response('question/successfully-submitted.html', ctxdict,
                                context_instance=RequestContext(request))
