package com.deer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;
@SpringBootApplication @EnableScheduling
public class DeerApplication {
    public static void main(String[] args) { SpringApplication.run(DeerApplication.class, args); }
}
