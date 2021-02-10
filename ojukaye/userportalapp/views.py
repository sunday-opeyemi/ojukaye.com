from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect
from django.urls import reverse_lazy, reverse
from django.contrib.auth.decorators import login_required
from .forms import Saysomething_form, Addmedia_form, Reply_form
from ojukaye.newsapp.models import news_table, comment_table, likeshare_table
from .models import userpost_table
from django.utils import timezone
from django.db.models import F
from itertools import chain

post_id = 0
# Create your views here.
@login_required
def user_portal(request, username):
    if request.method == 'POST':
        form = Saysomething_form(request.POST)
        if form.is_valid():
            userpost = form.cleaned_data['userpost']  
            post = userpost_table(post_content=userpost)
            post.user_id = request.user.id
            post.datetime = timezone.now()
            post.username = request.user.get_username()
            post.save()
    else:
        form = Saysomething_form()
    posted_news = news_table.objects.only('post_title').filter(username=username).order_by('post_id').reverse()
    comment_news = comment_table.objects.filter(username=username).reverse()
    share_news = news_table.objects.all().values('username', 'datetime', 'post_title').filter(likeshare_table__username=username, likeshare_table__share='share')
    user_post = userpost_table.objects.filter(username=request.user.get_username())
    # approved_news = list(sorted(chain(posted_news, comment_news, share_news, user_post), key=lambda val:val['datetime'], reverse=True))
    # approved_news = sorted(approved, key=lambda val:val['datetime'], reverse=True)
    approved_news = {'posted_news':posted_news, 'comment_news':comment_news, 'share_news':share_news, 'user_post':user_post}
    return render(request=request, template_name='userportalapp/userportal.html', context={'approved_news':approved_news,'form':form})

@login_required
def user_profile(request, userid):
    return render(request, 'userportalapp/profile.html')

@login_required
def addmedia(request):
    if request.method == 'POST':
        form = Addmedia_form(request.POST, request.FILES)
        if form.is_valid():
            userpost = form.cleaned_data['userpost']  
            picture = form.cleaned_data['picture'] 
            video = form.cleaned_data['video']
            audio = form.cleaned_data['audio'] 
            post = userpost_table(post_content=userpost, picture=picture, video=video, audio=audio)
            post.user_id = request.user.id
            post.datetime = timezone.now()
            post.username = request.user.get_username()
            post.save()
        return user_portal(request, request.user.get_username())
    else:
        # GET, generate blank form
        form = Addmedia_form()
        return render(request,'userportalapp/userpost_form.html', {'form':form})

def post_body(request, postid):
    global post_id
    # generate the contents to display on the page
    post_id = postid
    userpost = userpost_table.objects.filter(userp_id=postid)
    postcomment = comment_table.objects.filter(userp_id=postid)
    returned_value = {'postcomment':postcomment, 'userpost':userpost}
    return render(request,'userportalapp/post_body.html', {'returned_value':returned_value})

@login_required
def reply_post(request):
    if request.method == 'POST':
        # POST, generate form with data from the request
        form = Reply_form(request.POST, request.FILES)
        # check if it's valid:
        if form.is_valid():
            post_reply = form.cleaned_data['comment']
            photo = form.cleaned_data['picture']
            video = form.cleaned_data['video']
            audio = form.cleaned_data['audio']
            comment_post= comment_table(comment_post=post_reply, picture=photo, video=video, audio=audio)
            comment_post.userp_id = post_id
            comment_post.username = request.user.get_username()
            comment_post.comment_date = timezone.now()
            comment_post.save()
            # return to the news body page
            return  HttpResponsePermanentRedirect(reverse('postbody', args=(post_id,)))
    else:
        # GET, generate blank form 
        form = Reply_form()
        return render(request,'userportalapp/reply_post.html', {'form':form})

@login_required
def like_user(request, likeid):
    user_return = likeshare_table.objects.filter(comment_id=likeid, like='like', username=request.user.get_username())
    if user_return:
       user_return.delete()
       comment_table.objects.filter(comment_id=likeid).update(like_num=F('like_num') -1)
    else:
        likeshare = likeshare_table(username=request.user.get_username(), comment_id=likeid, like='like', userp_id=post_id)
        likeshare.save()
        comment_table.objects.filter(comment_id=likeid).update(like_num=F('like_num') +1)
    return post_body(request, post_id)

@login_required     
def unlike_user(request, unlikeid):
    user_return = likeshare_table.objects.filter(comment_id=unlikeid, unlike='unlike', username=request.user.get_username())
    if user_return:
        user_return.delete()
        comment_table.objects.filter(comment_id=unlikeid).update(unlike_num=F('unlike_num') -1)
    else:
        likeshare = likeshare_table(username=request.user.get_username(), comment_id=unlikeid, unlike='unlike', userp_id=post_id)
        likeshare.save()
        comment_table.objects.filter(comment_id=unlikeid).update(unlike_num=F('unlike_num') +1)
    return post_body(request, post_id)

@login_required
def share_user(request, shareid):
    likeshare = likeshare_table(username=request.user.get_username(), userp_id=post_id, share='share')
    likeshare.save()
    userpost_table.objects.filter(userp_id=shareid).update(share_num=F('share_num') +1)
    return post_body(request, post_id)

def follows(request, username):
    return render(request, 'userportalapp/follows.html')