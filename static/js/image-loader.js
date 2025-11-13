/**
 * 电影海报图片加载优化
 * 包括懒加载、错误处理和重试、淡入效果
 */
document.addEventListener('DOMContentLoaded', function() {
    // 修复TMDB图片URL路径
    function fixTmdbImageUrl(url) {
        if (!url) return url;
        // 如果不是完整的URL，但是是TMDB格式的路径（以/开头的图片文件）
        if (!url.startsWith('http') && 
            url.match(/^\/[a-zA-Z0-9]+\.(jpg|jpeg|png|webp)/) &&
            !url.startsWith('/static/')) {
            // 添加TMDB基础URL前缀
            return 'https://image.tmdb.org/t/p/w500' + url;
        }
        return url;
    }

    // 获取所有电影海报图片
    const movieImages = document.querySelectorAll('.movie-poster img, .image img');
    
    // 默认占位图和错误占位图路径
    const defaultPlaceholder = '/static/img/default-movie-placeholder.png';
    const errorPlaceholder = '/static/img/broken-image-placeholder.png';
    
    // 处理每个图片
    movieImages.forEach(img => {
        // 保存原始图片URL
        let originalSrc = img.getAttribute('src');
        
        // 修复TMDB图片URL
        originalSrc = fixTmdbImageUrl(originalSrc);
        
        // 更新图片src属性
        if (originalSrc !== img.getAttribute('src')) {
            img.setAttribute('src', originalSrc);
        }
        
        // 如果没有src属性或者src为空，使用默认占位图
        if (!originalSrc || originalSrc.trim() === '') {
            img.setAttribute('src', defaultPlaceholder);
            img.style.opacity = '1'; // 确保占位图可见
            return;
        }
        
        // 1. 检查图片是否已经加载完成
        if (img.complete && img.naturalHeight !== 0) {
            // 图片已加载完成且有效，确保可见
            img.style.opacity = '1';
            console.log('图片已缓存并加载完成:', originalSrc);
        } else {
            // 图片尚未加载完成，应用淡入效果
            img.style.opacity = '0';
            img.style.transition = 'opacity 0.3s ease-in';
        }
        
        // 2. 添加加载错误处理
        img.onerror = function() {
            // 标记图片加载失败
            img.dataset.loadFailed = 'true';
            
            // 显示错误占位图
            img.setAttribute('src', errorPlaceholder);
            
            // 确保图片可见
            img.style.opacity = '1';
            
            // 5秒后尝试重新加载一次
            setTimeout(() => {
                // 仅对网络图片（非占位图）重试
                if (originalSrc && 
                    originalSrc !== defaultPlaceholder && 
                    originalSrc !== errorPlaceholder) {
                    
                    // 添加随机参数避免缓存
                    const retrySrc = originalSrc.includes('?') 
                        ? `${originalSrc}&retry=${Date.now()}` 
                        : `${originalSrc}?retry=${Date.now()}`;
                    
                    // 在不影响用户体验的情况下重试
                    const tempImg = new Image();
                    tempImg.onload = function() {
                        // 重试成功，更新原图
                        img.setAttribute('src', retrySrc);
                        img.dataset.loadFailed = 'false';
                        img.style.opacity = '1';
                    };
                    tempImg.onerror = function() {
                        // 重试失败，保持错误占位图
                        console.log('图片重试加载失败:', originalSrc);
                    };
                    tempImg.src = retrySrc;
                }
            }, 5000);
        };
        
        // 3. 添加加载完成处理
        img.onload = function() {
            // 检查是否为错误占位图
            if (img.getAttribute('src') !== errorPlaceholder) {
                // 图片加载成功，淡入显示
                img.style.opacity = '1';
                img.dataset.loadFailed = 'false';
            }
        };
        
        // 4. 设置懒加载 (现代浏览器内置支持)
        if (!img.complete || img.naturalHeight === 0) {
            img.setAttribute('loading', 'lazy');
        }
        
        // 5. 对于不支持懒加载的浏览器，使用 Intersection Observer API
        if (!('loading' in HTMLImageElement.prototype) && (!img.complete || img.naturalHeight === 0)) {
            // 创建交叉观察器
            const imgObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const lazyImg = entry.target;
                        
                        // 仅当图片没有加载失败时设置src
                        if (lazyImg.dataset.loadFailed !== 'true') {
                            // 不要重置已经设置好的图片
                            if (lazyImg.src !== originalSrc) {
                                lazyImg.src = originalSrc;
                            }
                        }
                        
                        // 停止观察
                        observer.unobserve(lazyImg);
                    }
                });
            });
            
            // 开始观察
            imgObserver.observe(img);
        }
    });
    
    // 确保所有图片在5秒后无论如何都是可见的（安全机制）
    setTimeout(() => {
        movieImages.forEach(img => {
            if (parseFloat(img.style.opacity) < 1) {
                console.log('安全机制：强制显示图片');
                img.style.opacity = '1';
            }
        });
    }, 5000);
}); 