/**
 * 进度条初始化脚本
 * 确保页面加载时进度条样式能够正确应用
 */
document.addEventListener('DOMContentLoaded', function() {
    // 查找所有进度条元素
    const progressBars = document.querySelectorAll('.progress-bar');
    
    // 遍历并初始化每个进度条
    progressBars.forEach(function(bar) {
        // 获取进度值
        const value = parseFloat(bar.getAttribute('aria-valuenow') || 0);
        const percentage = Math.max(10, Math.min(100, value * 10));
        
        // 确保宽度样式正确应用
        bar.style.width = percentage + '%';
        
        // 为了触发CSS过渡效果，先设置宽度为0，然后用动画方式展示
        setTimeout(function() {
            // 添加过渡效果
            bar.style.transition = 'width 0.5s ease-in-out';
            // 重新设置宽度到目标值
            bar.style.width = percentage + '%';
        }, 50);
        
        // 根据分数值添加正确的样式类
        if (value >= 9) {
            ensureClass(bar, 'bg-primary');
        } else if (value >= 7) {
            ensureClass(bar, 'bg-success');
        } else if (value >= 4) {
            ensureClass(bar, 'bg-warning');
        } else {
            ensureClass(bar, 'bg-danger');
        }
    });
    
    // 辅助函数：确保元素有指定的CSS类
    function ensureClass(element, className) {
        if (!element.classList.contains(className)) {
            element.classList.add(className);
        }
    }
    
    // 检查进度条容器是否有正确的高度
    const progressContainers = document.querySelectorAll('.progress');
    progressContainers.forEach(function(container) {
        if (parseInt(window.getComputedStyle(container).height) === 0) {
            container.style.height = '10px';
        }
    });
}); 