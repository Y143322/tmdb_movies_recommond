/**
 * 电影页面交互脚本
 */
document.addEventListener('DOMContentLoaded', function() {
    // 获取当前URL的排序参数
    const urlParams = new URLSearchParams(window.location.search);
    const currentSort = urlParams.get('sort') || 'hot'; // 默认为hot
    
    // 处理排序选项点击事件 
    const sortOptions = document.querySelectorAll('.sort-option');
    
    if (sortOptions.length > 0) {
        // 为每个排序按钮添加点击事件
        sortOptions.forEach(option => {
            // 覆盖原有的onclick事件，确保能直接跳转
            option.addEventListener('click', function(e) {
                e.preventDefault();
                
                // 提供直观的视觉反馈
                this.style.transform = 'scale(0.95)';
                this.style.backgroundColor = '#4a00e0';
                this.style.color = 'white';
                
                // 显示加载状态
                const originalText = this.innerHTML;
                this.innerHTML = '<i class="fas fa-sync fa-spin"></i> 正在跳转...';
                
                // 直接跳转
                setTimeout(() => {
                    window.location.href = this.href;
                }, 300);
                
                return false;
            });
        });
        
        // 标记当前活动的排序选项
        sortOptions.forEach(option => {
            const optionUrl = new URL(option.href);
            const optionSort = optionUrl.searchParams.get('sort') || 'hot';
            
            if (optionSort === currentSort) {
                option.classList.add('active');
            }
        });
    }

    // 处理搜索表单
    const searchForm = document.querySelector('.search-form');
    const searchInput = document.querySelector('.search-input');
    
    if (searchForm && searchInput) {
        searchForm.addEventListener('submit', function(e) {
            if (searchInput.value.trim() === '') {
                e.preventDefault();
                searchInput.focus();
                
                // 添加震动效果提示用户输入
                searchForm.classList.add('shake');
                setTimeout(() => {
                    searchForm.classList.remove('shake');
                }, 500);
            }
        });
        
        // 自动聚焦搜索框
        if (!searchInput.value) {
            setTimeout(() => {
                searchInput.focus();
            }, 500);
        }
    }
    
    // 初始化标题动态溢出提示
    const movieTitles = document.querySelectorAll('.movie-card .title');
    if (movieTitles.length > 0) {
        movieTitles.forEach(title => {
            if (title.scrollWidth > title.clientWidth) {
                title.title = title.textContent; // 添加标题属性显示完整文本
            }
        });
    }
}); 