# Built-in and Django imports
import logging
from django import template
register = template.Library()

# 3rd part imports
logger = logging.getLogger('quest')

# Idea from: http://lybniz2.sourceforge.net/safeeval.html
from math import *
safe_list = ['acos', 'acosh', 'asin', 'asinh', 'atan', 'atan2', 'atanh',
             'ceil', 'copysign', 'cos', 'cosh', 'degrees', 'e',
             'exp', 'fabs', 'factorial', 'floor', 'fmod', 'frexp', 'fsum',
             'hypot', 'isinf', 'isnan', 'ldexp', 'log', 'log10', 'log1p',
             'modf', 'pi', 'pow', 'radians', 'sin', 'sinh', 'sqrt',
             'tan', 'tanh', 'trunc']
safe_dict = dict([ (k, locals().get(k, None)) for k in safe_list ])
safe_dict['all'] = all
safe_dict['abs'] = abs
safe_dict['bin'] = bin
safe_dict['oct'] = oct
safe_dict['hex'] = hex
safe_dict['round'] = round
safe_dict['len'] = len
safe_dict['sum'] = sum
safe_dict['float'] = float
safe_dict['int'] = int
safe_dict['pow'] = pow
safe_dict['divmod'] = divmod
safe_dict['str'] = str
safe_dict['min'] = min
safe_dict['max'] = max
safe_dict['any'] = any
safe_dict['bool'] = bool
safe_dict['complex'] = complex


@register.tag
def quick_eval(parser, token):
    """
    Set up up the "{% evaluate %}" tag for use in the templates.
    Code from Django's documentation
    """
    #try:
        # split_contents() knows not to split quoted strings.
    out = token.split_contents()
    #except ValueError:
    #    raise template.TemplateSyntaxError("%r tag requires a single #argument" % token.contents.split()[0])

    if len(out) == 2:
        tag_name, format_string = out
        sig_figs = None
    elif len(out) == 3:
        tag_name, format_string, sig_figs = out
        sig_figs = int(sig_figs.strip(' ').strip(','))
    else:
        template.TemplateSyntaxError("%r tag requires either 1 or 2 arguments")

    if not (format_string[0] == format_string[-1] and \
                                             format_string[0] in ('"', "'")):
        raise template.TemplateSyntaxError("%r tag's argument should be in quotes" % tag_name)

    return EvaluateString(format_string[1:-1], sig_figs)

class EvaluateString(template.Node):
    """ Does the actual work of evaluating the node. """
    def __init__(self, format_string, sig_figs=None):
        self.format_string = format_string
        self.sig_figs = sig_figs

    def render(self, context):
        """
        Render the ``quick_eval`` template tag
        """
        # Use the most recent context to evaluate the template.
        ctx = context.dicts[-1].copy()

        # TODO(KGD): convert every entry to Numpy floats (even ints)

        # TODO(KGD): http://lucumr.pocoo.org/2011/2/1/exec-in-python/

        # Execute the string provided by the user
        # The mode must be 'exec' to compile a module, 'single' to compile a
        # single (interactive) statement, or 'eval' to compile an expression.
        #code = compile(self.format_string, "<internal>", "eval")
        try:
            out = eval(self.format_string, safe_dict, ctx)
        except Exception as e:
            out = str(e)

        # Clean up the output
        from decimal import Decimal, Context
        out = Context(prec=self.sig_figs, Emax=999,).create_decimal(str(out))
        out = out.to_eng_string()

        return out
