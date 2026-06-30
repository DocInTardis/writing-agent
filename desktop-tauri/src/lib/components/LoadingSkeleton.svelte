<div class="skeleton-wrapper">
  <div class="skeleton-header">
    <div class="skeleton-line skeleton-title"></div>
    <div class="skeleton-line skeleton-subtitle"></div>
  </div>
  <div class="skeleton-content">
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line short"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line short"></div>
  </div>
</div>

<style>
  .skeleton-wrapper {
    padding: 24px;
    animation: fadeIn 0.3s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .skeleton-header {
    margin-bottom: 24px;
  }

  .skeleton-line {
    height: 16px;
    background: linear-gradient(90deg, 
      rgba(200, 180, 150, 0.2) 0%, 
      rgba(200, 180, 150, 0.3) 50%, 
      rgba(200, 180, 150, 0.2) 100%
    );
    background-size: 200% 100%;
    border-radius: 8px;
    margin-bottom: 12px;
    animation: shimmer 1.5s infinite;
  }

  @keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }

  .skeleton-title {
    height: 24px;
    width: 60%;
  }

  .skeleton-subtitle {
    height: 14px;
    width: 40%;
  }

  .skeleton-line.short {
    width: 70%;
  }
</style>
