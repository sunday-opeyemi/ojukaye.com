from django.shortcuts import render
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect
from .forms import News_post_form, Comment_form, SignUpForm, Search_bar_form
from ojukaye.newsapp.models import news_table, comment_table, likeshare_table
from datetime import datetime
from django.utils import timezone
from django.db.models import F
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

category = ''
post_headline = ''
post_id = 0
# Create your views here.
@login_required
def homenews(request, url_name='general_news'):
    global category
    if request.method == 'POST':
        form = Search_bar_form(request.POST)
        if form.is_valid():
            search = form.cleaned_data['search']  
            approved_news = news_table.objects.only('post_title').filter(approved='approved').filter(post_title__icontains=search).order_by('post_id')
    else:
        form = Search_bar_form()
        if url_name == 'general_news':
            approved_news = news_table.objects.only('post_title').filter(approved='approved').order_by('post_id')
            category = ''
        else:
            approved_news = news_table.objects.only('post_title').filter(category=url_name).order_by('post_id')
            category = url_name
    # Add pagination to the template
    paginator = Paginator(approved_news, 3)
    page_number = request.GET.get('page')
    approved_news_obj = paginator.get_page(page_number)
    returned_values = {'approved_news':approved_news_obj, 'headline':category, 'form':form} 
    return render(request, 'newsapp/homenewsfeed.html', {'returned_values':returned_values})

class SignUpView(generic.CreateView):
    # form_class = UserCreationForm
    form_class = SignUpForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

def homepage(request):
    if request.method == 'POST':
        form = Search_bar_form(request.POST)
        if form.is_valid():
            search = form.cleaned_data['search']  
            approved_news = news_table.objects.only('post_title').filter(post_title__icontains=search, approved='approved').order_by('post_id')
    else:
        form = Search_bar_form()
        approved_news = news_table.objects.only('post_title').filter(approved='approved').order_by('post_id')
    # Add pagination to the template
    paginator = Paginator(approved_news, 3)
    page_number = request.GET.get('page')
    approved_news_obj = paginator.get_page(page_number)
    return render(request=request, template_name='index.html', context={'approved_news':approved_news_obj,'form':form})

@login_required
def post_news(request):
    if request.method == 'POST':
        # POST, generate form with data from the request
        form = News_post_form(request.POST, request.FILES)
        # check if it's valid:
        if form.is_valid():
            post_title = form.cleaned_data['post_title']
            post_news = form.cleaned_data['news_post']
            news_sourse = form.cleaned_data['news_source']
            photo = form.cleaned_data['picture']
            video = form.cleaned_data['video']
            audio = form.cleaned_data['audio']
            news_post = news_table(post_title=post_title, news_post=post_news, picture=photo, video=video, audio=audio, approved = "unapprove", post_source=news_sourse)
            news_post.category = category
            news_post.datetime = timezone.now()
            news_post.username = request.user.get_username()
            news_post.save()
            approved_news = news_table.objects.only('post_title').filter(category=category)
            returned_values = {'approved_news':approved_news, 'headline':category}
            return  HttpResponsePermanentRedirect(reverse('homenewsfeed', args=(category,)))
    else:
        # GET, generate blank form
        form = News_post_form()
        return_form = {'form':form, 'category':category}
        return render(request,'newsapp/post_news.html', {'return_form':return_form})

@login_required
def comment_post(request):
    if request.method == 'POST':
        # POST, generate form with data from the request
        form = Comment_form(request.POST, request.FILES)
        # check if it's valid:
        if form.is_valid():
            post_reply = form.cleaned_data['comment']
            photo = form.cleaned_data['picture']
            video = form.cleaned_data['video']
            audio = form.cleaned_data['audio']
            comment_post= comment_table(comment_post=post_reply, picture=photo, video=video, audio=audio)
            comment_post.post_id = post_id
            comment_post.post_title = post_headline
            comment_post.username = request.user.get_username()
            comment_post.comment_date = timezone.now()
            comment_post.save()
            # return to the news body page
            return  HttpResponsePermanentRedirect(reverse('newsbody', args=(post_headline,)))
    else:
        # GET, generate blank form
        form = Comment_form()
        return_form = {'form':form, 'headline':post_headline}
        return render(request,'newsapp/comment_post.html', {'return_form':return_form})

def news_body(request, headline):
    global post_headline, post_id
    # generate the contents to display on the page
    post_headline = headline
    approved_news = news_table.objects.filter(post_title=headline)
    post_id = approved_news.values('post_id')
    comment_news = comment_table.objects.filter(post_title=headline)
    returned_value = {'comment_news':comment_news, 'approved_news':approved_news}
    return render(request,'newsapp/news_body.html', {'returned_value':returned_value})

@login_required
def like_comment(request, likeid):
    user_return = likeshare_table.objects.filter(comment_id=likeid, like='like', username=request.user.get_username())
    if user_return:
       user_return.delete()
       comment_table.objects.filter(comment_id=likeid).update(like_num=F('like_num') -1)
    else:
        likeshare = likeshare_table(username=request.user.get_username(), comment_id=likeid, like='like', post_id=post_id)
        likeshare.save()
        comment_table.objects.filter(comment_id=likeid).update(like_num=F('like_num') +1)
    return news_body(request, post_headline)

    # update_like = comment_table.objects.get(comment_id=likeid)
    # # Update the name value
    # update_like.like_num = update_like.like_num + 1
    # # Call save() with the update_fields arg and a list of record fields to update selectively
    # update_like.save(update_fields=['like_num'])

@login_required     
def unlike_comment(request, unlikeid):
    user_return = likeshare_table.objects.filter(comment_id=unlikeid, unlike='unlike', username=request.user.get_username())
    if user_return:
        user_return.delete()
        comment_table.objects.filter(comment_id=unlikeid).update(unlike_num=F('unlike_num') -1)
    else:
        likeshare = likeshare_table(username=request.user.get_username(), comment_id=unlikeid, unlike='unlike', post_id=post_id)
        likeshare.save()
        comment_table.objects.filter(comment_id=unlikeid).update(unlike_num=F('unlike_num') +1)
    return news_body(request, post_headline)

@login_required
def share_post(request, shareid):
    likeshare = likeshare_table(username=request.user.get_username(), post_id=post_id, share='share')
    likeshare.save()
    news_table.objects.filter(post_id=shareid).update(share_num=F('share_num') +1)
    return news_body(request, post_headline)

    