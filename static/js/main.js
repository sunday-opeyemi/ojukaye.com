// ===== MAIN JAVASCRIPT =====

// DOM Ready
document.addEventListener('DOMContentLoaded', function() {
    initMobileMenu();
    initImageFallback();
    initInfiniteScroll();
    initCommentReplies();
    initLikeButtons();
    initBookmarkButtons();
    initShareButtons();
    initFollowButtons();
    initNewsFilters();
    initBannerSlider();
    initPostCreation();
    initCommentLoadMore();
    initSearchAutocomplete();
    initDarkMode();
});

// ===== MOBILE MENU =====
function initMobileMenu() {
    const menuBtn = document.querySelector('.mobile-menu-btn');
    const mobileMenu = document.querySelector('.mobile-menu');
    
    if (menuBtn && mobileMenu) {
        menuBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            mobileMenu.classList.toggle('active');
            
            const icon = menuBtn.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-bars');
                icon.classList.toggle('fa-times');
            }
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', function(e) {
            if (!menuBtn.contains(e.target) && !mobileMenu.contains(e.target)) {
                mobileMenu.classList.remove('active');
                const icon = menuBtn.querySelector('i');
                if (icon) {
                    icon.classList.add('fa-bars');
                    icon.classList.remove('fa-times');
                }
            }
        });
    }
}

// ===== IMAGE FALLBACK =====
function initImageFallback() {
    const images = document.querySelectorAll('img');
    
    images.forEach(img => {
        img.addEventListener('error', function() {
            this.onerror = null;
            
            // Try to get category from parent or data attribute
            const category = this.dataset.category || 'default';
            const placeholders = {
                default: 'https://images.unsplash.com/photo-1588681664899-f142ff2dc9b1?w=800&q=80',
                politics: 'https://images.unsplash.com/photo-1551135049-8a33b2fb2f7f?w=800&q=80',
                business: 'https://images.unsplash.com/photo-1665686306577-32e6bfa1d1d1?w=800&q=80',
                technology: 'https://images.unsplash.com/photo-1518709268805-4e9042af2176?w=800&q=80',
                sports: 'https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=800&q=80',
                entertainment: 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800&q=80',
                health: 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?w=800&q=80',
                education: 'https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=800&q=80'
            };
            
            this.src = placeholders[category.toLowerCase()] || placeholders.default;
        });
    });
}

// ===== INFINITE SCROLL =====
function initInfiniteScroll() {
    const postsContainer = document.querySelector('.posts-container');
    const loadingIndicator = document.querySelector('.loading-indicator');
    let currentPage = 1;
    let loading = false;
    let hasMore = true;
    
    if (!postsContainer) return;
    
    window.addEventListener('scroll', function() {
        if (!hasMore || loading) return;
        
        const scrollPosition = window.innerHeight + window.scrollY;
        const threshold = document.documentElement.scrollHeight - 1000;
        
        if (scrollPosition >= threshold) {
            loadMorePosts();
        }
    });
    
    async function loadMorePosts() {
        loading = true;
        if (loadingIndicator) loadingIndicator.style.display = 'block';
        
        currentPage++;
        
        try {
            const url = new URL(window.location.href);
            url.searchParams.set('page', currentPage);
            
            const response = await fetch(url.toString(), {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (response.ok) {
                const html = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newPosts = doc.querySelector('.posts-container');
                
                if (newPosts) {
                    postsContainer.insertAdjacentHTML('beforeend', newPosts.innerHTML);
                    initLikeButtons();
                    initBookmarkButtons();
                    initShareButtons();
                    initImageFallback();
                } else {
                    hasMore = false;
                }
            } else {
                hasMore = false;
            }
        } catch (error) {
            console.error('Error loading more posts:', error);
            hasMore = false;
        } finally {
            loading = false;
            if (loadingIndicator) loadingIndicator.style.display = 'none';
        }
    }
}

// ===== COMMENT REPLIES =====
function initCommentReplies() {
    document.querySelectorAll('.reply-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            
            const commentId = this.dataset.commentId;
            const commentAuthor = this.dataset.author;
            const replyForm = document.querySelector('.comment-form');
            
            if (replyForm) {
                const textarea = replyForm.querySelector('textarea');
                const parentInput = replyForm.querySelector('input[name="parent_id"]');
                
                if (parentInput) parentInput.value = commentId;
                
                if (textarea) {
                    textarea.focus();
                    textarea.placeholder = `Reply to @${commentAuthor}...`;
                }
            }
        });
    });
}

// ===== LIKE BUTTONS =====
function initLikeButtons() {
    document.querySelectorAll('.like-btn').forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.preventDefault();
            
            if (!isAuthenticated()) {
                window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname);
                return;
            }
            
            const postId = this.dataset.postId;
            const countSpan = this.querySelector('.like-count');
            const icon = this.querySelector('i');
            
            try {
                const response = await fetch(`/post/${postId}/like/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    if (countSpan) countSpan.textContent = data.like_count;
                    
                    if (data.liked) {
                        this.classList.add('liked');
                        icon.classList.remove('far');
                        icon.classList.add('fas');
                    } else {
                        this.classList.remove('liked');
                        icon.classList.remove('fas');
                        icon.classList.add('far');
                    }
                }
            } catch (error) {
                console.error('Error liking post:', error);
            }
        });
    });
}

// ===== BOOKMARK BUTTONS =====
function initBookmarkButtons() {
    document.querySelectorAll('.bookmark-btn').forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.preventDefault();
            
            if (!isAuthenticated()) {
                window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname);
                return;
            }
            
            const postId = this.dataset.postId;
            const icon = this.querySelector('i');
            
            try {
                const response = await fetch(`/post/${postId}/bookmark/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    
                    if (data.bookmarked) {
                        this.classList.add('bookmarked');
                        icon.classList.remove('far');
                        icon.classList.add('fas');
                        
                        // Show notification
                        showNotification('Post saved to bookmarks!', 'success');
                    } else {
                        this.classList.remove('bookmarked');
                        icon.classList.remove('fas');
                        icon.classList.add('far');
                        
                        showNotification('Post removed from bookmarks', 'info');
                    }
                }
            } catch (error) {
                console.error('Error bookmarking post:', error);
            }
        });
    });
}

// ===== SHARE BUTTONS =====
function initShareButtons() {
    document.querySelectorAll('.share-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            
            const postTitle = this.dataset.title;
            const postUrl = this.dataset.url;
            
            if (navigator.share) {
                navigator.share({
                    title: postTitle,
                    url: postUrl
                }).catch(console.error);
            } else {
                // Fallback - copy to clipboard
                navigator.clipboard.writeText(postUrl).then(() => {
                    showNotification('Link copied to clipboard!', 'success');
                }).catch(() => {
                    prompt('Copy this link:', postUrl);
                });
            }
        });
    });
}

// ===== FOLLOW BUTTONS =====
// Follow button functionality
document.querySelectorAll('.btn-follow').forEach(btn => {
    btn.addEventListener('click', function(e) {
        e.preventDefault();
        
        const username = this.dataset.username;
        const csrfToken = getCsrfToken();
        
        // Disable button to prevent double-click
        this.disabled = true;
        const originalText = this.innerHTML;
        this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        
        fetch(`/follow/${username}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw err; });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                if (data.is_following || data.followed) {
                    this.innerHTML = '<i class="fas fa-check"></i> Following';
                    this.classList.add('following');
                } else {
                    this.innerHTML = '<i class="fas fa-plus"></i> Follow';
                    this.classList.remove('following');
                }
                
                // Update follower count in profile stats if exists
                const followerCountEl = document.querySelector('.follower-count, .stat-value.followers');
                if (followerCountEl && data.followers_count !== undefined) {
                    followerCountEl.textContent = data.followers_count;
                }
                
                // Show success message
                showNotification(data.message, 'success');
            } else {
                showNotification(data.error || 'An error occurred', 'error');
                this.innerHTML = originalText;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showNotification(error.error || 'An error occurred. Please try again.', 'error');
            this.innerHTML = originalText;
        })
        .finally(() => {
            this.disabled = false;
        });
    });
});

// Helper function to get CSRF token
function getCsrfToken() {
    // Try to get from cookie
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
    
    if (cookieValue) return cookieValue;
    
    // Try to get from meta tag
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken) return metaToken.getAttribute('content');
    
    // Try to get from form input
    const inputToken = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (inputToken) return inputToken.value;
    
    return '{{ csrf_token }}';
}

// Notification function
function showNotification(message, type = 'info') {
    // Check if notification container exists, if not create it
    let container = document.querySelector('.notification-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'notification-container';
        document.body.appendChild(container);
        
        // Add styles if not exists
        const style = document.createElement('style');
        style.textContent = `
            .notification-container {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
            }
            .notification {
                background: white;
                border-radius: 8px;
                padding: 12px 20px;
                margin-bottom: 10px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                display: flex;
                align-items: center;
                gap: 10px;
                animation: slideIn 0.3s ease;
                border-left: 4px solid;
            }
            .notification.success { border-left-color: #10b981; }
            .notification.error { border-left-color: #ef4444; }
            .notification.info { border-left-color: #3b82f6; }
            .notification.warning { border-left-color: #f59e0b; }
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    let icon = '';
    if (type === 'success') icon = '<i class="fas fa-check-circle"></i>';
    else if (type === 'error') icon = '<i class="fas fa-exclamation-circle"></i>';
    else if (type === 'warning') icon = '<i class="fas fa-exclamation-triangle"></i>';
    else icon = '<i class="fas fa-info-circle"></i>';
    
    notification.innerHTML = `${icon} <span>${message}</span>`;
    container.appendChild(notification);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ===== NEWS FILTERS =====
function initNewsFilters() {
    const filterLinks = document.querySelectorAll('.news-filter-link');
    const categoryLinks = document.querySelectorAll('.category-link');
    
    filterLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            filterLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');
            
            const filter = this.dataset.filter;
            const url = new URL(window.location.href);
            url.searchParams.set('filter', filter);
            window.location.href = url.toString();
        });
    });
    
    categoryLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            categoryLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');
            
            const category = this.dataset.category;
            const url = new URL(window.location.href);
            
            if (category === 'all') {
                url.searchParams.delete('category');
            } else {
                url.searchParams.set('category', category);
            }
            
            window.location.href = url.toString();
        });
    });
}

// ===== BANNER SLIDER =====
function initBannerSlider() {
    const bannerSliders = document.querySelectorAll('.banner-slider');
    
    bannerSliders.forEach(slider => {
        const slides = slider.querySelectorAll('.banner-slide');
        const dotsContainer = slider.querySelector('.slider-dots');
        const prevBtn = slider.querySelector('.slider-prev');
        const nextBtn = slider.querySelector('.slider-next');
        
        if (!slides.length) return;
        
        let currentSlide = 0;
        let slideInterval;
        
        // Create dots
        if (dotsContainer) {
            slides.forEach((_, index) => {
                const dot = document.createElement('button');
                dot.classList.add('slider-dot');
                if (index === 0) dot.classList.add('active');
                dot.addEventListener('click', () => goToSlide(index));
                dotsContainer.appendChild(dot);
            });
        }
        
        function goToSlide(index) {
            slides.forEach(slide => slide.classList.remove('active'));
            slides[index].classList.add('active');
            
            const dots = dotsContainer?.querySelectorAll('.slider-dot');
            dots?.forEach((dot, i) => {
                dot.classList.toggle('active', i === index);
            });
            
            currentSlide = index;
        }
        
        function nextSlide() {
            currentSlide = (currentSlide + 1) % slides.length;
            goToSlide(currentSlide);
        }
        
        function prevSlide() {
            currentSlide = (currentSlide - 1 + slides.length) % slides.length;
            goToSlide(currentSlide);
        }
        
        if (prevBtn) prevBtn.addEventListener('click', prevSlide);
        if (nextBtn) nextBtn.addEventListener('click', nextSlide);
        
        // Auto advance slides
        slideInterval = setInterval(nextSlide, 5000);
        
        // Pause on hover
        slider.addEventListener('mouseenter', () => clearInterval(slideInterval));
        slider.addEventListener('mouseleave', () => {
            slideInterval = setInterval(nextSlide, 5000);
        });
        
        // Initialize first slide
        goToSlide(0);
    });
}

// ===== POST CREATION =====
function initPostCreation() {
    const postForm = document.querySelector('.create-post-form');
    const postTypeRadios = document.querySelectorAll('input[name="post_type"]');
    const sourceUrlField = document.querySelector('.source-url-field');
    const imageUploadBtn = document.querySelector('.image-upload-btn');
    const imagePreview = document.querySelector('.image-preview');
    
    if (postTypeRadios.length) {
        postTypeRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                if (sourceUrlField) {
                    if (this.value === 'user_news') {
                        sourceUrlField.style.display = 'block';
                        sourceUrlField.querySelector('input').required = true;
                    } else {
                        sourceUrlField.style.display = 'none';
                        sourceUrlField.querySelector('input').required = false;
                    }
                }
            });
        });
    }
    
    if (imageUploadBtn) {
        imageUploadBtn.addEventListener('change', function(e) {
            const file = e.target.files[0];
            
            if (file && imagePreview) {
                const reader = new FileReader();
                
                reader.onload = function(e) {
                    imagePreview.innerHTML = `
                        <div class="preview-image">
                            <img src="${e.target.result}" alt="Preview">
                            <button type="button" class="remove-image-btn">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    `;
                    
                    const removeBtn = imagePreview.querySelector('.remove-image-btn');
                    if (removeBtn) {
                        removeBtn.addEventListener('click', function() {
                            imagePreview.innerHTML = '';
                            imageUploadBtn.value = '';
                        });
                    }
                };
                
                reader.readAsDataURL(file);
            }
        });
    }
}

// ===== COMMENT LOAD MORE =====
function initCommentLoadMore() {
    const loadMoreBtn = document.querySelector('.load-more-comments');
    
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            
            const postId = this.dataset.postId;
            const offset = this.dataset.offset || 12;
            
            try {
                const response = await fetch(`/post/${postId}/comments/?offset=${offset}`, {
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                
                if (response.ok) {
                    const html = await response.text();
                    const commentsContainer = document.querySelector('.comments-list');
                    
                    if (commentsContainer) {
                        commentsContainer.insertAdjacentHTML('beforeend', html);
                        this.dataset.offset = parseInt(offset) + 12;
                        
                        // Check if there are more comments
                        if (this.dataset.offset >= this.dataset.total) {
                            this.style.display = 'none';
                        }
                    }
                }
            } catch (error) {
                console.error('Error loading more comments:', error);
            }
        });
    }
}

// ===== SEARCH AUTOCOMPLETE =====
function initSearchAutocomplete() {
    const searchInput = document.querySelector('.search-input');
    
    if (searchInput) {
        let debounceTimer;
        
        searchInput.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            
            const query = this.value.trim();
            
            if (query.length < 2) return;
            
            debounceTimer = setTimeout(async () => {
                try {
                    const response = await fetch(`/api/search/suggest/?q=${encodeURIComponent(query)}`);
                    
                    if (response.ok) {
                        const suggestions = await response.json();
                        showSearchSuggestions(suggestions);
                    }
                } catch (error) {
                    console.error('Error fetching suggestions:', error);
                }
            }, 300);
        });
    }
}

function showSearchSuggestions(suggestions) {
    // Implementation depends on UI design
    console.log('Search suggestions:', suggestions);
}

// ===== DARK MODE =====
function initDarkMode() {
    const darkModeToggle = document.querySelector('.dark-mode-toggle');
    
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', async function(e) {
            e.preventDefault();
            
            try {
                const response = await fetch('/api/toggle-dark-mode/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                
                if (response.ok) {
                    const data = await response.json();
                    document.body.classList.toggle('dark-mode', data.dark_mode);
                }
            } catch (error) {
                console.error('Error toggling dark mode:', error);
            }
        });
    }
}

// ===== AUTH PAGES FUNCTIONS =====

/**
 * Initialize password toggle functionality for auth pages
 */
function initAuthPasswordToggles() {
    document.querySelectorAll('.password-toggle').forEach(button => {
        // Remove existing listeners to prevent duplicates
        button.removeEventListener('click', handlePasswordToggle);
        button.addEventListener('click', handlePasswordToggle);
    });
}

function handlePasswordToggle(e) {
    e.preventDefault();
    const passwordInput = this.previousElementSibling;
    const icon = this.querySelector('i');
    
    if (!passwordInput) return;
    
    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        passwordInput.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
}

/**
 * Initialize account type selector for register page
 */
function initAccountTypeSelector() {
    const accountRadios = document.querySelectorAll('input[name="account_type"]');
    const businessFields = document.querySelector('.business-fields');
    
    if (!accountRadios.length || !businessFields) return;
    
    function toggleBusinessFields() {
        const selectedRadio = document.querySelector('input[name="account_type"]:checked');
        if (selectedRadio && selectedRadio.value === 'business') {
            businessFields.style.display = 'block';
            businessFields.style.animation = 'slideDown 0.3s ease';
            
            // Make business fields required
            const businessInputs = businessFields.querySelectorAll('input[required]');
            businessInputs.forEach(input => {
                input.required = true;
            });
        } else {
            businessFields.style.display = 'none';
            
            // Remove required from business fields
            const businessInputs = businessFields.querySelectorAll('input');
            businessInputs.forEach(input => {
                input.required = false;
            });
        }
    }
    
    // Initial state
    toggleBusinessFields();
    
    // Add event listeners
    accountRadios.forEach(radio => {
        radio.removeEventListener('change', toggleBusinessFields);
        radio.addEventListener('change', toggleBusinessFields);
    });
}

/**
 * Initialize auth form validation
 */
function initAuthFormValidation() {
    const authForms = document.querySelectorAll('.auth-form');
    
    authForms.forEach(form => {
        form.removeEventListener('submit', handleAuthSubmit);
        form.addEventListener('submit', handleAuthSubmit);
    });
}

function handleAuthSubmit(e) {
    // Remove existing error messages
    this.querySelectorAll('.form-error').forEach(el => el.remove());
    this.querySelectorAll('.form-input.error').forEach(el => {
        el.classList.remove('error');
    });
    
    let isValid = true;
    
    // Validate required fields
    const requiredInputs = this.querySelectorAll('[required]');
    requiredInputs.forEach(input => {
        if (!input.value.trim()) {
            isValid = false;
            showFieldError(input, 'This field is required');
        }
    });
    
    // Email validation
    const emailInput = this.querySelector('input[type="email"]');
    if (emailInput && emailInput.value.trim()) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(emailInput.value.trim())) {
            isValid = false;
            showFieldError(emailInput, 'Please enter a valid email address');
        }
    }
    
    // Username validation
    const usernameInput = this.querySelector('input[name="username"]');
    if (usernameInput && usernameInput.value.trim()) {
        const usernameRegex = /^[a-zA-Z0-9@./+/-/_]+$/;
        if (!usernameRegex.test(usernameInput.value.trim())) {
            isValid = false;
            showFieldError(usernameInput, 'Username can only contain letters, numbers, and @/./+/-/_');
        }
    }
    
    // Password validation (register page)
    const passwordInput = this.querySelector('input[name="password1"]');
    const confirmInput = this.querySelector('input[name="password2"]');
    
    if (passwordInput && confirmInput) {
        // Password strength
        if (passwordInput.value.length < 8) {
            isValid = false;
            showFieldError(passwordInput, 'Password must be at least 8 characters');
        }
        
        // Password match
        if (passwordInput.value !== confirmInput.value) {
            isValid = false;
            showFieldError(confirmInput, 'Passwords do not match');
        }
    }
    
    // Business validation
    const businessRadio = document.querySelector('input[name="account_type"][value="business"]');
    if (businessRadio && businessRadio.checked) {
        const businessName = this.querySelector('input[name="business_name"]');
        if (businessName && !businessName.value.trim()) {
            isValid = false;
            showFieldError(businessName, 'Business name is required');
        }
        
        const businessEmail = this.querySelector('input[name="business_email"]');
        if (businessEmail && !businessEmail.value.trim()) {
            isValid = false;
            showFieldError(businessEmail, 'Business email is required');
        }
    }
    
    // Terms agreement validation (register page)
    const termsCheckbox = this.querySelector('input[name="agree_terms"]');
    if (termsCheckbox && !termsCheckbox.checked) {
        isValid = false;
        showNotification('You must agree to the Terms of Service and Privacy Policy', 'error');
    }
    
    if (!isValid) {
        e.preventDefault();
    }
}

function showFieldError(input, message) {
    input.classList.add('error');
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'form-error';
    errorDiv.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
    
    // Insert after the input's parent wrapper or after the input
    if (input.parentElement.classList.contains('password-wrapper')) {
        input.parentElement.parentElement.appendChild(errorDiv);
    } else {
        input.parentElement.appendChild(errorDiv);
    }
}

/**
 * Initialize auth page animations
 */
function initAuthAnimations() {
    // Add slide down animation to business fields
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(20px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        
        .auth-left {
            animation: slideIn 0.5s ease;
        }
        
        .auth-right {
            animation: slideIn 0.5s ease 0.1s both;
        }
    `;
    document.head.appendChild(style);
}

// ===== REMEMBER ME FUNCTIONALITY =====
function initRememberMe() {
    const rememberCheckbox = document.getElementById('remember');
    const usernameInput = document.getElementById('id_username');
    
    if (rememberCheckbox && usernameInput) {
        // Load saved username
        const savedUsername = localStorage.getItem('remembered_username');
        if (savedUsername) {
            usernameInput.value = savedUsername;
            rememberCheckbox.checked = true;
        }
        
        // Save username when checkbox is checked
        rememberCheckbox.addEventListener('change', function() {
            if (this.checked && usernameInput.value.trim()) {
                localStorage.setItem('remembered_username', usernameInput.value.trim());
            } else {
                localStorage.removeItem('remembered_username');
            }
        });
        
        // Update saved username when input changes
        usernameInput.addEventListener('input', function() {
            if (rememberCheckbox.checked && this.value.trim()) {
                localStorage.setItem('remembered_username', this.value.trim());
            }
        });
    }
}
/**
 * Initialize social login buttons
 */
function initSocialLogin() {
    document.querySelectorAll('.btn-social').forEach(btn => {
        btn.addEventListener('click', function(e) {
            // Add loading state
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Redirecting...';
            this.style.opacity = '0.7';
            this.style.pointerEvents = 'none';
            
            // Let the default link behavior happen
            setTimeout(() => {
                this.innerHTML = originalText;
                this.style.opacity = '1';
                this.style.pointerEvents = 'auto';
            }, 5000);
        });
    });
}

/**
 * Initialize all auth page functions
 */
function initAuthPages() {
    if (document.querySelector('.auth-page')) {
        initAuthPasswordToggles();
        initAccountTypeSelector();
        initAuthFormValidation();
        initAuthAnimations();
        initRememberMe();
        initSocialLogin();
    }
}

// Add to your DOMContentLoaded event
document.addEventListener('DOMContentLoaded', function() {
    // ... your existing init functions ...
    
    // Initialize auth pages
    initAuthPages();
});

// Also initialize on page load via Turbolinks/PJAX if you're using it
document.addEventListener('turbolinks:load', function() {
    initAuthPages();
});

// ===== UTILITY FUNCTIONS =====

// Get CSRF Token
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

// Check if user is authenticated
function isAuthenticated() {
    return document.querySelector('.nav-profile-btn') !== null;
}

// Show notification
function showNotification(message, type = 'info') {
    const container = document.querySelector('.messages-container');
    
    if (!container) {
        const newContainer = document.createElement('div');
        newContainer.className = 'messages-container';
        document.querySelector('.main-content')?.prepend(newContainer);
        container = newContainer;
    }
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <div class="alert-content">
            <i class="fas ${type === 'success' ? 'fa-check-circle' : 
                           type === 'error' ? 'fa-exclamation-circle' :
                           type === 'warning' ? 'fa-exclamation-triangle' : 
                           'fa-info-circle'}"></i>
            <span>${message}</span>
        </div>
        <button class="alert-close">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    container.appendChild(alert);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        alert.remove();
    }, 5000);
    
    // Close button
    alert.querySelector('.alert-close').addEventListener('click', () => {
        alert.remove();
    });
}
// Dark Mode Toggle
function initDarkMode() {
    const darkModeToggle = document.querySelector('.dark-mode-toggle');
    const theme = localStorage.getItem('theme') || 'light';
    
    document.documentElement.setAttribute('data-theme', theme);
    
    if (darkModeToggle) {
        const icon = darkModeToggle.querySelector('i');
        icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        
        darkModeToggle.addEventListener('click', function(e) {
            e.preventDefault();
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            
            const icon = this.querySelector('i');
            icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        });
    }
}

// Check system preference on first visit
function setInitialTheme() {
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('theme', 'light');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    setInitialTheme();
    initDarkMode();
});


document.addEventListener('DOMContentLoaded', initDarkMode);

function fixProfileTextVisibility() {
    // Target all profile meta spans
    const profileMetaSpans = document.querySelectorAll('.profile-header-meta span');
    
    profileMetaSpans.forEach(span => {
        // Force text color
        span.style.color = 'var(--text-tertiary)';
        
        // Also force any child elements
        const childElements = span.querySelectorAll('*');
        childElements.forEach(child => {
            if (child.tagName !== 'I' && child.tagName !== 'A') {
                child.style.color = 'var(--text-tertiary)';
            }
        });
    });
    
    // Target location and date specifically
    const locationSpans = document.querySelectorAll('.profile-header-meta span:has(.fa-map-marker-alt)');
    locationSpans.forEach(span => {
        const textNode = span.childNodes[1]; // The text node after the icon
        if (textNode) {
            span.style.color = 'var(--text-tertiary)';
        }
    });
    
    const dateSpans = document.querySelectorAll('.profile-header-meta span:has(.fa-calendar-alt), .profile-header-meta span:has(.fa-calendar)');
    dateSpans.forEach(span => {
        span.style.color = 'var(--text-tertiary)';
    });
}

// Run on page load
document.addEventListener('DOMContentLoaded', function() {
    fixProfileTextVisibility();
});

// Also run after any dynamic content changes
const observer = new MutationObserver(function(mutations) {
    fixProfileTextVisibility();
});

observer.observe(document.body, {
    childList: true,
    subtree: true
});
// Add to your existing main.js file
document.addEventListener('DOMContentLoaded', function() {
    // Fix mobile menu
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const mobileMenu = document.querySelector('.mobile-menu');
    
    if (mobileMenuBtn && mobileMenu) {
        mobileMenuBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            mobileMenu.classList.toggle('active');
            
            const icon = this.querySelector('i');
            icon.classList.toggle('fa-bars');
            icon.classList.toggle('fa-times');
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', function(e) {
            if (!mobileMenuBtn.contains(e.target) && !mobileMenu.contains(e.target)) {
                mobileMenu.classList.remove('active');
                const icon = mobileMenuBtn.querySelector('i');
                icon.classList.add('fa-bars');
                icon.classList.remove('fa-times');
            }
        });
    }
    
    // Fix banner slider touch
    const bannerSliders = document.querySelectorAll('.banner-slider');
    bannerSliders.forEach(slider => {
        let touchStartX = 0;
        let touchEndX = 0;
        
        slider.addEventListener('touchstart', e => {
            touchStartX = e.changedTouches[0].screenX;
        }, { passive: true });
        
        slider.addEventListener('touchend', e => {
            touchEndX = e.changedTouches[0].screenX;
            handleSwipe();
        }, { passive: true });
        
        function handleSwipe() {
            const swipeThreshold = 50;
            const diff = touchStartX - touchEndX;
            
            if (Math.abs(diff) > swipeThreshold) {
                const nextBtn = slider.querySelector('.slider-next');
                const prevBtn = slider.querySelector('.slider-prev');
                
                if (diff > 0 && nextBtn) {
                    nextBtn.click();
                } else if (diff < 0 && prevBtn) {
                    prevBtn.click();
                }
            }
        }
    });
    
    // Fix responsive font sizes
    function adjustFontSizes() {
        const width = window.innerWidth;
        const root = document.documentElement;
        
        if (width <= 360) {
            root.style.fontSize = '14px';
        } else if (width <= 400) {
            root.style.fontSize = '15px';
        } else if (width <= 576) {
            root.style.fontSize = '16px';
        } else {
            root.style.fontSize = '16px';
        }
    }
    
    window.addEventListener('resize', adjustFontSizes);
    adjustFontSizes();
});
// ===== PASSWORD TOGGLE FIX FOR AUTH PAGES =====
function initPasswordToggles() {
    console.log('Initializing password toggles');
    const toggleButtons = document.querySelectorAll('.password-toggle');
    
    toggleButtons.forEach(button => {
        // Remove any existing listeners to prevent duplicates
        button.removeEventListener('click', handlePasswordToggle);
        button.addEventListener('click', handlePasswordToggle);
    });
}

function handlePasswordToggle(e) {
    e.preventDefault();
    e.stopPropagation();
    
    const button = e.currentTarget;
    const wrapper = button.closest('.password-wrapper');
    if (!wrapper) return;
    
    const passwordInput = wrapper.querySelector('input[type="password"], input[type="text"]');
    const icon = button.querySelector('i');
    
    if (!passwordInput || !icon) return;
    
    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        passwordInput.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
    
    // Keep focus on input
    passwordInput.focus();
}

// ===== BUSINESS FIELDS TOGGLE =====
function initBusinessFieldsToggle() {
    const accountRadios = document.querySelectorAll('input[name="account_type"]');
    const businessFields = document.querySelector('.business-fields');
    
    if (!accountRadios.length || !businessFields) return;
    
    function toggleBusinessFields() {
        const selectedRadio = document.querySelector('input[name="account_type"]:checked');
        if (selectedRadio && selectedRadio.value === 'business') {
            businessFields.style.display = 'block';
            // Make business fields required
            const requiredInputs = businessFields.querySelectorAll('input[required]');
            requiredInputs.forEach(input => input.required = true);
        } else {
            businessFields.style.display = 'none';
            // Remove required from business fields
            const inputs = businessFields.querySelectorAll('input');
            inputs.forEach(input => input.required = false);
        }
    }
    
    // Initial state
    toggleBusinessFields();
    
    // Add event listeners
    accountRadios.forEach(radio => {
        radio.addEventListener('change', toggleBusinessFields);
    });
}
// ===== QUICK FLASH MESSAGES =====
function initFlashMessages() {
    const alerts = document.querySelectorAll('.alert');
    
    alerts.forEach(alert => {
        // Auto-dismiss after 3 seconds
        setTimeout(() => {
            alert.style.transition = 'opacity 0.3s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 3000);
        
        // Add close button if not present
        if (!alert.querySelector('.alert-close')) {
            const closeBtn = document.createElement('button');
            closeBtn.className = 'alert-close';
            closeBtn.innerHTML = '<i class="fas fa-times"></i>';
            closeBtn.addEventListener('click', () => alert.remove());
            alert.appendChild(closeBtn);
        }
    });
}
document.addEventListener('DOMContentLoaded', function() {
    // Your existing init functions
    initMobileMenu();
    initImageFallback();
    initInfiniteScroll();
    initCommentReplies();
    initLikeButtons();
    initBookmarkButtons();
    initShareButtons();
    initFollowButtons();
    initNewsFilters();
    initBannerSlider();
    initPostCreation();
    initCommentLoadMore();
    initSearchAutocomplete();
    initDarkMode();
    
    // NEW: Auth page specific functions
    if (document.querySelector('.auth-page')) {
        initPasswordToggles();
        initBusinessFieldsToggle();
        initAuthFormValidation();
        initRememberMe();
        initFlashMessages();
    }
    
    // Fix profile text visibility
    fixProfileTextVisibility();
    
    // Set up mutation observer for dynamic content
    setupMutationObserver();
});

// Add mutation observer to handle dynamically loaded content
function setupMutationObserver() {
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length) {
                // Reinitialize password toggles if new auth content is added
                if (document.querySelector('.auth-page')) {
                    initPasswordToggles();
                }
                // Reinitialize image fallback
                initImageFallback();
                // Fix profile text
                fixProfileTextVisibility();
            }
        });
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}
// ===== MODAL MESSAGE HANDLER =====
function checkForModalMessages() {
    // Check if there are messages in session to display as modal
    fetch('/api/get-modal-messages/', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.messages && data.messages.length > 0) {
            // Show each message as modal (with slight delay between)
            data.messages.forEach((msg, index) => {
                setTimeout(() => {
                    showMessageModal(msg.message, msg.tags || 'info');
                }, index * 500);
            });
        }
    })
    .catch(error => console.error('Error checking messages:', error));
}

// Call this on page load
document.addEventListener('DOMContentLoaded', function() {
    checkForModalMessages();
});