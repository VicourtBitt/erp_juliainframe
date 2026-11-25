from django.core.paginator import Paginator

PER_PAGE_CHOICES = (10, 25, 50, 100)


def paginate(request, object_list, *, per_page=25, param="page"):
    """Paginate ``object_list`` from the querystring.

    ``param`` names the page parameter so several tables on one page paginate
    independently (``?page=2&sales_page=3``). The page size comes from
    ``<param>_size`` when it is one of PER_PAGE_CHOICES.
    """
    size_param = f"{param}_size"
    try:
        size = int(request.GET.get(size_param, per_page))
    except (TypeError, ValueError):
        size = per_page
    if size not in PER_PAGE_CHOICES:
        size = per_page
    page = Paginator(object_list, size).get_page(request.GET.get(param))
    page.param = param
    page.size_param = size_param
    page.size = size
    page.size_choices = PER_PAGE_CHOICES
    page.elided_range = page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1)
    return page
