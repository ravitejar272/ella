from django.http import Http404, HttpResponseRedirect
from django import newforms as forms
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.contrib.formtools.preview import FormPreview

from ella.core.middleware import get_current_request
from ella.core.views import get_templates_from_listing
from ella.interviews.models import Question, Answer


class ReplyForm(forms.Form):
    """ A form representing the reply, it also contains the mechanism needed to actually save the reply. """
    content = Answer._meta.get_field('content').formfield()

    def __init__(self, interview, interviewees, question, *args, **kwargs):
        self.interview = interview
        self.question = question

        super(ReplyForm, self).__init__(*args, **kwargs)

        if len(interviewees) == 1:
            self.interviewee = interviewees[0]
        else:
            from django.utils.translation import ugettext
            self.fields['interviewee'] = forms.ChoiceField(
                    choices=[ (u'', u'--------') ] + [ (i.pk, unicode(i)) for i in interviewees ],
                    label=ugettext('Interviewee')
)

    def save(self):
        if not self.is_valid():
            raise ValueError, 'Cannot save an invalid form.'

        if hasattr(self, 'interviewee'):
            interviewee = self.interviewee.pk
        else:
            interviewee = self.cleaned_data['interviewee']

        request = get_current_request()
        if 'HTTP_X_FORWARDED_FOR' in request.META:
            ip = request.META['HTTP_X_FORWARDED_FOR']
        else:
            ip = request.META['REMOTE_ADDR']

        a = Answer(
                question=self.question,
                interviewee_id=interviewee,
                content=self.cleaned_data['content'],
)
        a.save()
        return a

def detail(request, context):
    """ Custom object detail function that adds a QuestionForm to the context. """
    interview = context['object']
    context['form'] = QuestionForm()
    return render_to_response(
        get_templates_from_listing('object.html', context['listing']),
        context,
        context_instance=RequestContext(request)
)

def unanswered(request, bits, context):
    """ Display unanswered questions via rendering page/content_type/interviews.interview/unanswered.html template. """
    if bits:
        # invalid URL
        raise Http404

    interview = context['object']
    context['form'] = QuestionForm()
    return render_to_response(
        get_templates_from_listing('unanswered.html', context['listing']),
        context,
        context_instance=RequestContext(request)
)

def reply(request, bits, context):
    """
    If called without parameters will display a list of questions
    (via rendering page/content_type/interviews.interview/reply.html template).

    Can be also called as reply/PK/ which will then display a ReplyForm for the given question.

    Raises Http404 on any error or missing permissions.
    """
    interview = context['object']

    interviewees = interview.get_interviewees(request.user)
    if not interviewees:
        # no permission
        raise Http404

    elif not bits:
        # list of all questions
        return render_to_response(
            get_templates_from_listing('reply.html', context['listing']),
            context,
            context_instance=RequestContext(request)
)

    elif len(bits) != 1:
        # some bogus URL
        raise Http404

    # no point in caching individual questions
    question = get_object_or_404(
            Question,
            pk=bits[0],
            interview=interview
)

    form = ReplyForm(interview, interviewees, question, request.POST or None)
    if form.is_valid():
        form.save()
        # go back to the question list
        return HttpResponseRedirect('..')

    context['form'] = form
    context['question'] = question

    return render_to_response(
        get_templates_from_listing('answer_form.html', context['listing']),
        context,
        context_instance=RequestContext(request)
)

class QuestionForm(forms.Form):
    """ Ask a question. If current user is authenticated, don't ask him for nick/email. """
    nickname = Question._meta.get_field('nickname').formfield(required=True)
    email = Question._meta.get_field('email').formfield()
    content = Question._meta.get_field('content').formfield()

    def __init__(self, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)

        request = get_current_request()
        # if a user is logged in, do not ask for nick and/or email
        if request.user.is_authenticated():
            del self.fields['nickname']
            del self.fields['email']


class QuestionFormPreview(FormPreview):
    """ FormPreview subclass that handles the question asking mechanism. """
    @property
    def preview_template(self):
        return get_templates_from_listing('ask_preview.html', self.state['listing']),

    @property
    def form_template(self):
        return get_templates_from_listing('ask_form.html', self.state['listing']),

    def parse_params(self, bits, context):
        """ Store the context provided by ella to self.state. """
        if not context['object'].can_ask() or bits:
            raise Http404
        self.state.update(context)

    def done(self, request, cleaned_data):
        """ Save the question itself. """

        if 'HTTP_X_FORWARDED_FOR' in request.META:
            ip = request.META['HTTP_X_FORWARDED_FOR']
        else:
            ip = request.META['REMOTE_ADDR']

        question = Question(interview=self.state['object'], ip_address=ip, **cleaned_data)

        if request.user.is_authenticated():
            question.user = request.user

        question.save()

        return HttpResponseRedirect('..')

