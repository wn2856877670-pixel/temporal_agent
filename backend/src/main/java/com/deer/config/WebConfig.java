package com.deer.config;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.*;
import org.springframework.web.servlet.HandlerInterceptor;
import jakarta.servlet.http.*;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
@Configuration
public class WebConfig implements WebMvcConfigurer {
    @Value("${deer.internal-token}") String token;
    @Value("${deer.media-root}") String root;
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            public boolean preHandle(HttpServletRequest req,HttpServletResponse res,Object handler) throws Exception {
                String supplied=req.getHeader("X-Internal-Token");
                if(token.length()<24 || supplied==null || !MessageDigest.isEqual(token.getBytes(StandardCharsets.UTF_8),supplied.getBytes(StandardCharsets.UTF_8))) {
                    res.sendError(401); return false;
                } return true;
            }
        }).addPathPatterns("/api/internal/**");
    }
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/media/business/**").addResourceLocations(Path.of(root).toAbsolutePath().toUri().toString()+"/");
    }
}
