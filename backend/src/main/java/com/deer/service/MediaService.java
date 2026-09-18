package com.deer.service;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Value;
import java.nio.file.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
@Service
public class MediaService {
    public final Path root;
    public MediaService(@Value("${deer.media-root}") String root) { this.root=Path.of(root).toAbsolutePath().normalize(); }
    public String validate(String value,String taskId) {
        try {
            Path path=Path.of(value).toRealPath();
            Path allowed=root.resolve("results").resolve(taskId).toRealPath();
            if(!path.startsWith(allowed) || !Files.isRegularFile(path)) throw new IllegalArgumentException("Invalid result path");
            return path.toString();
        } catch(Exception e) { throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Result media missing or outside task directory"); }
    }
    public String url(String value) {
        if(value==null) return null;
        Path path=Path.of(value).toAbsolutePath().normalize();
        if(!path.startsWith(root)) return null;
        return "/media/business/"+root.relativize(path).toString().replace('\\','/');
    }
}
